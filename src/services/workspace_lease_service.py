"""Workspace lease service for write serialization and concurrency control.

Provides service-level orchestration for lease acquisition, renewal, and release
with transaction-safe conflict behavior and expiration-based recovery.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.db.models import WorkspaceLease
from src.db.repositories.workspace_lease_repository import WorkspaceLeaseRepository


class LeaseResult(Enum):
    """Result codes for lease operations."""

    ACQUIRED = auto()  # Lease acquired successfully
    CONFLICT = auto()  # Another holder has active lease (retryable)
    EXPIRED_RECOVERED = auto()  # Expired lease recovered and acquired
    NOT_FOUND = auto()  # No active lease found for operation
    HOLDER_MISMATCH = auto()  # Holder identity mismatch
    RENEWED = auto()  # Lease renewed successfully
    RELEASED = auto()  # Lease released successfully


@dataclass
class LeaseAcquisitionResult:
    """Result of a lease acquisition attempt."""

    success: bool
    result: LeaseResult
    lease: Optional[WorkspaceLease]
    message: str


@dataclass
class LeaseReleaseResult:
    """Result of a lease release attempt."""

    success: bool
    result: LeaseResult
    released_at: Optional[datetime]
    message: str


@dataclass
class LeaseRenewalResult:
    """Result of a lease renewal attempt."""

    success: bool
    result: LeaseResult
    lease: Optional[WorkspaceLease]
    new_expires_at: Optional[datetime]
    message: str


class WorkspaceLeaseService:
    """Service for workspace lease lifecycle management.

    This service provides the control-plane layer for workspace write
    serialization with:
    - Transaction-safe lease acquisition with conflict detection
    - Automatic expiration recovery for crashed holders
    - Heartbeat/renewal for long-running operations
    - Deterministic release in all success/failure branches

    The service is fail-closed: ambiguous lease states result in
    denial rather than allowing potential race conditions.
    """

    # Default lease TTL: 5 minutes
    DEFAULT_LEASE_TTL_SECONDS = 300

    # Minimum allowed TTL: 10 seconds (prevents accidental immediate expiry)
    MIN_LEASE_TTL_SECONDS = 10

    # Maximum allowed TTL: 1 hour (prevents indefinite locks)
    MAX_LEASE_TTL_SECONDS = 3600

    def __init__(self, session: Session):
        """Initialize the lease service.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session
        self._repository = WorkspaceLeaseRepository(session)

    def acquire_lease(
        self,
        workspace_id: UUID,
        holder_run_id: str,
        holder_identity: str,
        ttl_seconds: Optional[int] = None,
    ) -> LeaseAcquisitionResult:
        """Acquire a lease for workspace write operations.

        Attempts to acquire an exclusive lease for the workspace. If another
        holder has an active lease, returns a retryable CONFLICT result.
        If an expired lease exists, it is recovered and a new lease acquired.

        Args:
            workspace_id: UUID of the workspace to acquire lease for.
            holder_run_id: Unique identifier for the run acquiring the lease.
            holder_identity: Identity of the lease holder (e.g., user ID).
            ttl_seconds: Lease time-to-live in seconds (default: 300).

        Returns:
            LeaseAcquisitionResult with success status and lease details.

        Raises:
            ValueError: If ttl_seconds is outside allowed range.
        """
        ttl = self._validate_ttl(ttl_seconds)

        try:
            # Attempt to acquire lease atomically
            lease = self._repository.acquire_active_lease(
                workspace_id=workspace_id,
                holder_run_id=holder_run_id,
                holder_identity=holder_identity,
                ttl_seconds=ttl,
            )

            if lease:
                # Check if this was an expired lease recovery
                # (we can tell by checking if there were previous leases)
                existing_active = self._repository.get_active_lease(workspace_id)
                if existing_active and existing_active.id == lease.id:
                    # Check the age - if acquired very recently, might be recovery
                    time_since_acquisition = datetime.utcnow() - lease.acquired_at
                    if time_since_acquisition.total_seconds() < 1:
                        # Check if there was a previous expired lease by looking
                        # at version > 1 or checking for released leases
                        if lease.version > 1:
                            return LeaseAcquisitionResult(
                                success=True,
                                result=LeaseResult.EXPIRED_RECOVERED,
                                lease=lease,
                                message=(
                                    f"Lease acquired after recovering expired lease "
                                    f"for workspace {workspace_id}"
                                ),
                            )

                return LeaseAcquisitionResult(
                    success=True,
                    result=LeaseResult.ACQUIRED,
                    lease=lease,
                    message=f"Lease acquired for workspace {workspace_id}",
                )

            # No lease acquired - check if there's an active lease
            active_lease = self._repository.get_active_lease(workspace_id)
            if active_lease:
                return LeaseAcquisitionResult(
                    success=False,
                    result=LeaseResult.CONFLICT,
                    lease=None,
                    message=(
                        f"Workspace {workspace_id} has active lease held by "
                        f"{active_lease.holder_identity} "
                        f"(expires at {active_lease.expires_at.isoformat()})"
                    ),
                )

            # No active lease found - this is ambiguous, fail closed
            return LeaseAcquisitionResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                lease=None,
                message=(
                    f"Lease acquisition failed for workspace {workspace_id}: "
                    f"ambiguous state - no active lease but acquisition refused"
                ),
            )

        except Exception as e:
            # Fail closed on any error
            return LeaseAcquisitionResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                lease=None,
                message=f"Lease acquisition failed: {str(e)}",
            )

    def release_lease(
        self,
        workspace_id: UUID,
        holder_run_id: Optional[str] = None,
        require_holder_match: bool = True,
    ) -> LeaseReleaseResult:
        """Release a workspace lease.

        Releases the active lease for the workspace. If require_holder_match
        is True, only releases if the holder_run_id matches.

        Args:
            workspace_id: UUID of the workspace.
            holder_run_id: Optional run ID to verify ownership.
            require_holder_match: If True, require holder_run_id to match.

        Returns:
            LeaseReleaseResult with release status.
        """
        try:
            # If we require holder match, pass the holder_run_id
            # Otherwise pass None to release any active lease
            release_holder_id = holder_run_id if require_holder_match else None

            released = self._repository.release_lease(
                workspace_id=workspace_id,
                holder_run_id=release_holder_id,
            )

            if released:
                return LeaseReleaseResult(
                    success=True,
                    result=LeaseResult.RELEASED,
                    released_at=datetime.utcnow(),
                    message=f"Lease released for workspace {workspace_id}",
                )

            # Check if lease exists but holder doesn't match
            if require_holder_match and holder_run_id:
                active_lease = self._repository.get_active_lease(workspace_id)
                if active_lease and active_lease.holder_run_id != holder_run_id:
                    return LeaseReleaseResult(
                        success=False,
                        result=LeaseResult.HOLDER_MISMATCH,
                        released_at=None,
                        message=(
                            f"Lease holder mismatch for workspace {workspace_id}: "
                            f"expected {holder_run_id}, "
                            f"found {active_lease.holder_run_id}"
                        ),
                    )

            return LeaseReleaseResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                released_at=None,
                message=f"No active lease found for workspace {workspace_id}",
            )

        except Exception as e:
            return LeaseReleaseResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                released_at=None,
                message=f"Lease release failed: {str(e)}",
            )

    def renew_lease(
        self,
        workspace_id: UUID,
        holder_run_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> LeaseRenewalResult:
        """Renew (extend) a workspace lease.

        Extends the expiration time of an active lease. Used for heartbeat
        during long-running operations.

        Args:
            workspace_id: UUID of the workspace.
            holder_run_id: Run ID to verify ownership.
            ttl_seconds: New TTL in seconds (default: same as initial).

        Returns:
            LeaseRenewalResult with renewal status.

        Raises:
            ValueError: If ttl_seconds is outside allowed range.
        """
        ttl = self._validate_ttl(ttl_seconds)

        try:
            lease = self._repository.renew_lease(
                workspace_id=workspace_id,
                holder_run_id=holder_run_id,
                ttl_seconds=ttl,
            )

            if lease:
                return LeaseRenewalResult(
                    success=True,
                    result=LeaseResult.RENEWED,
                    lease=lease,
                    new_expires_at=lease.expires_at,
                    message=(
                        f"Lease renewed for workspace {workspace_id}, "
                        f"expires at {lease.expires_at.isoformat()}"
                    ),
                )

            # Check if lease exists but is expired
            active_lease = self._repository.get_active_lease(workspace_id)
            if not active_lease:
                return LeaseRenewalResult(
                    success=False,
                    result=LeaseResult.NOT_FOUND,
                    lease=None,
                    new_expires_at=None,
                    message=(
                        f"Cannot renew lease for workspace {workspace_id}: "
                        f"no active lease found (may have expired)"
                    ),
                )

            # Lease exists but holder mismatch
            if active_lease.holder_run_id != holder_run_id:
                return LeaseRenewalResult(
                    success=False,
                    result=LeaseResult.HOLDER_MISMATCH,
                    lease=None,
                    new_expires_at=None,
                    message=(
                        f"Lease holder mismatch for workspace {workspace_id}: "
                        f"expected {holder_run_id}, "
                        f"found {active_lease.holder_run_id}"
                    ),
                )

            # Ambiguous state - fail closed
            return LeaseRenewalResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                lease=None,
                new_expires_at=None,
                message=f"Lease renewal failed: ambiguous state",
            )

        except Exception as e:
            return LeaseRenewalResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                lease=None,
                new_expires_at=None,
                message=f"Lease renewal failed: {str(e)}",
            )

    def get_active_lease(self, workspace_id: UUID) -> Optional[WorkspaceLease]:
        """Get the active lease for a workspace if one exists.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            WorkspaceLease if active lease exists, None otherwise.
        """
        return self._repository.get_active_lease(workspace_id)

    def has_active_lease(self, workspace_id: UUID) -> bool:
        """Check if a workspace has an active lease.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            True if active lease exists, False otherwise.
        """
        return self._repository.has_active_lease(workspace_id)

    def _validate_ttl(self, ttl_seconds: Optional[int]) -> int:
        """Validate and normalize TTL value.

        Args:
            ttl_seconds: Requested TTL, or None for default.

        Returns:
            Validated TTL in seconds.

        Raises:
            ValueError: If TTL is outside allowed range.
        """
        if ttl_seconds is None:
            return self.DEFAULT_LEASE_TTL_SECONDS

        if ttl_seconds < self.MIN_LEASE_TTL_SECONDS:
            raise ValueError(
                f"TTL must be at least {self.MIN_LEASE_TTL_SECONDS} seconds, "
                f"got {ttl_seconds}"
            )

        if ttl_seconds > self.MAX_LEASE_TTL_SECONDS:
            raise ValueError(
                f"TTL must be at most {self.MAX_LEASE_TTL_SECONDS} seconds, "
                f"got {ttl_seconds}"
            )

        return ttl_seconds

    def force_release_expired(self, workspace_id: UUID) -> LeaseReleaseResult:
        """Force release an expired lease (administrative operation).

        This bypasses holder verification and should only be used by
        administrative workers for cleanup.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            LeaseReleaseResult with release status.
        """
        try:
            released = self._repository.release_lease(
                workspace_id=workspace_id,
                holder_run_id=None,  # Don't check holder
            )

            if released:
                return LeaseReleaseResult(
                    success=True,
                    result=LeaseResult.RELEASED,
                    released_at=datetime.utcnow(),
                    message=f"Expired lease force-released for workspace {workspace_id}",
                )

            return LeaseReleaseResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                released_at=None,
                message=f"No lease to release for workspace {workspace_id}",
            )

        except Exception as e:
            return LeaseReleaseResult(
                success=False,
                result=LeaseResult.NOT_FOUND,
                released_at=None,
                message=f"Force release failed: {str(e)}",
            )
