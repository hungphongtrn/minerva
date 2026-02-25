"""Repository for workspace lease operations.

Provides lease acquisition, release, and query methods for workspace
write serialization. Uses optimistic locking and unique constraints
to prevent race conditions.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.db.models import WorkspaceLease


class LeaseAcquisitionError(Exception):
    """Exception raised when lease acquisition fails due to lock contention."""

    def __init__(
        self,
        message: str,
        workspace_id: UUID,
        original_error: Optional[Exception] = None,
    ):
        self.workspace_id = workspace_id
        self.original_error = original_error
        super().__init__(message)


class WorkspaceLeaseRepository:
    """Repository for workspace lease lifecycle operations."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def acquire_active_lease(
        self,
        workspace_id: UUID,
        holder_run_id: Optional[str] = None,
        holder_identity: Optional[str] = None,
        ttl_seconds: int = 300,
        use_locking: bool = True,
    ) -> Optional[WorkspaceLease]:
        """Attempt to acquire an active lease for a workspace.

        Uses explicit locking and conflict detection to handle race conditions.
        Only succeeds if no active lease exists for the workspace.

        This method is cross-database compatible (SQLite, PostgreSQL).

        Args:
            workspace_id: UUID of the workspace to acquire lease for.
            holder_run_id: Optional identifier for the run holding the lease.
            holder_identity: Optional identity of the lease holder.
            ttl_seconds: Time-to-live for the lease in seconds (default: 5 min).
            use_locking: If True, use row-level locking (default: True).

        Returns:
            WorkspaceLease if acquired successfully, None if workspace
            already has an active lease.

        Raises:
            LeaseAcquisitionError: If lock acquisition times out due to contention.
        """
        try:
            # First, release any expired leases for this workspace
            self._release_expired_leases(workspace_id)

            # Check if there's already an active (non-expired, non-released) lease
            # Use FOR UPDATE locking if available to prevent race conditions
            existing = self._get_active_lease_for_update(
                workspace_id, use_locking=use_locking
            )
            if existing:
                return None

            # No active lease - create one
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            lease = WorkspaceLease(
                workspace_id=workspace_id,
                holder_run_id=holder_run_id,
                holder_identity=holder_identity,
                expires_at=expires_at,
                acquired_at=datetime.utcnow(),
                version=1,
            )

            self._session.add(lease)
            self._session.flush()

            return lease

        except OperationalError as e:
            # Handle lock timeout/contention errors
            error_str = str(e).lower()
            if any(
                keyword in error_str
                for keyword in ["lock", "timeout", "busy", "deadlock"]
            ):
                raise LeaseAcquisitionError(
                    f"Lock timeout acquiring lease for workspace {workspace_id}: {e}",
                    workspace_id=workspace_id,
                    original_error=e,
                ) from e
            raise

    def _release_expired_leases(self, workspace_id: UUID) -> int:
        """Release all expired leases for a workspace.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Number of leases released.
        """
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.expires_at < datetime.utcnow(),
                WorkspaceLease.released_at.is_(None),
            )
        )

        expired_leases = self._session.execute(stmt).scalars().all()
        count = 0
        for lease in expired_leases:
            lease.released_at = datetime.utcnow()
            count += 1

        if count > 0:
            self._session.flush()

        return count

    def _get_active_lease_for_update(
        self,
        workspace_id: UUID,
        use_locking: bool = True,
    ) -> Optional[WorkspaceLease]:
        """Get active lease for workspace with row locking if supported.

        Args:
            workspace_id: UUID of the workspace.
            use_locking: If True, use FOR UPDATE locking (default: True).

        Returns:
            Active WorkspaceLease if exists, None otherwise.
        """
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.expires_at > datetime.utcnow(),
                WorkspaceLease.released_at.is_(None),
            )
        )

        # Use FOR UPDATE locking to serialize concurrent lease acquisitions
        if use_locking:
            stmt = stmt.with_for_update()

        return self._session.execute(stmt).scalar_one_or_none()

    def release_lease(
        self,
        workspace_id: UUID,
        holder_run_id: Optional[str] = None,
    ) -> bool:
        """Release an active lease for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            holder_run_id: Optional holder_run_id to verify ownership.

        Returns:
            True if lease was released, False if no active lease found
            or holder mismatch.
        """
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.released_at.is_(None),
            )
        )

        if holder_run_id:
            stmt = stmt.where(WorkspaceLease.holder_run_id == holder_run_id)

        lease = self._session.execute(stmt).scalar_one_or_none()

        if not lease:
            return False

        lease.released_at = datetime.utcnow()
        self._session.flush()

        return True

    def renew_lease(
        self,
        workspace_id: UUID,
        holder_run_id: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> Optional[WorkspaceLease]:
        """Renew an active lease, extending its expiration time.

        Args:
            workspace_id: UUID of the workspace.
            holder_run_id: Optional holder_run_id to verify ownership.
            ttl_seconds: New TTL from now in seconds.

        Returns:
            WorkspaceLease if renewed, None if no active lease found.
        """
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.expires_at > datetime.utcnow(),
                WorkspaceLease.released_at.is_(None),
            )
        )

        if holder_run_id:
            stmt = stmt.where(WorkspaceLease.holder_run_id == holder_run_id)

        lease = self._session.execute(stmt).scalar_one_or_none()

        if not lease:
            return None

        lease.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        lease.version += 1
        self._session.flush()

        return lease

    def get_active_lease(self, workspace_id: UUID) -> Optional[WorkspaceLease]:
        """Get the currently active lease for a workspace.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            WorkspaceLease if an active (non-expired, non-released) lease
            exists, None otherwise.
        """
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.expires_at > datetime.utcnow(),
                WorkspaceLease.released_at.is_(None),
            )
        )

        return self._session.execute(stmt).scalar_one_or_none()

    def has_active_lease(self, workspace_id: UUID) -> bool:
        """Check if workspace currently has an active lease.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            True if active lease exists, False otherwise.
        """
        return self.get_active_lease(workspace_id) is not None
