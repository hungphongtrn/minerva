"""Repository for workspace lease operations.

Provides lease acquisition, release, and query methods for workspace
write serialization. Uses optimistic locking and unique constraints
to prevent race conditions.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.db.models import WorkspaceLease


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
    ) -> Optional[WorkspaceLease]:
        """Attempt to acquire an active lease for a workspace.

        Uses upsert with conflict resolution to handle race conditions.
        Only succeeds if no active lease exists for the workspace.

        Args:
            workspace_id: UUID of the workspace to acquire lease for.
            holder_run_id: Optional identifier for the run holding the lease.
            holder_identity: Optional identity of the lease holder.
            ttl_seconds: Time-to-live for the lease in seconds (default: 5 min).

        Returns:
            WorkspaceLease if acquired successfully, None if workspace
            already has an active lease.
        """
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        # Use insert with on_conflict_do_nothing for atomic lease acquisition
        # This leverages the partial unique index on active leases
        stmt = (
            insert(WorkspaceLease)
            .values(
                workspace_id=workspace_id,
                holder_run_id=holder_run_id,
                holder_identity=holder_identity,
                expires_at=expires_at,
                acquired_at=datetime.utcnow(),
                version=1,
            )
            .on_conflict_do_nothing(
                index_elements=["workspace_id"], where="released_at IS NULL"
            )
            .returning(WorkspaceLease)
        )

        result = self._session.execute(stmt)
        lease = result.scalar_one_or_none()

        if lease:
            self._session.flush()
            return lease

        # Lease not acquired - check if there's an expired one we can take
        return self._try_acquire_expired_lease(
            workspace_id, holder_run_id, holder_identity, ttl_seconds
        )

    def _try_acquire_expired_lease(
        self,
        workspace_id: UUID,
        holder_run_id: Optional[str],
        holder_identity: Optional[str],
        ttl_seconds: int,
    ) -> Optional[WorkspaceLease]:
        """Try to acquire an expired lease by releasing it first.

        Args:
            workspace_id: UUID of the workspace.
            holder_run_id: Optional run ID for the new holder.
            holder_identity: Optional identity for the new holder.
            ttl_seconds: TTL for the new lease.

        Returns:
            WorkspaceLease if expired lease was acquired, None otherwise.
        """
        # Find expired unreleased lease
        stmt = select(WorkspaceLease).where(
            and_(
                WorkspaceLease.workspace_id == workspace_id,
                WorkspaceLease.expires_at < datetime.utcnow(),
                WorkspaceLease.released_at.is_(None),
            )
        )

        existing = self._session.execute(stmt).scalar_one_or_none()
        if not existing:
            return None

        # Release the expired lease
        existing.released_at = datetime.utcnow()
        self._session.flush()

        # Create new lease
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        new_lease = WorkspaceLease(
            workspace_id=workspace_id,
            holder_run_id=holder_run_id,
            holder_identity=holder_identity,
            expires_at=expires_at,
            acquired_at=datetime.utcnow(),
            version=1,
        )

        self._session.add(new_lease)
        self._session.flush()

        return new_lease

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
