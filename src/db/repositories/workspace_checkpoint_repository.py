"""Repository for workspace checkpoint operations.

Provides CRUD and query methods for checkpoint metadata management,
including active checkpoint pointer resolution and fallback chain traversal.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session

from src.db.models import (
    WorkspaceCheckpoint,
    CheckpointState,
    WorkspaceActiveCheckpoint,
)


class WorkspaceCheckpointRepository:
    """Repository for workspace checkpoint lifecycle operations."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        workspace_id: UUID,
        checkpoint_id: str,
        version: str,
        storage_key: str,
        created_by_run_id: Optional[str] = None,
        previous_checkpoint_id: Optional[UUID] = None,
        manifest_json: Optional[str] = None,
    ) -> WorkspaceCheckpoint:
        """Create a new checkpoint record.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: Unique checkpoint identifier (string).
            version: Checkpoint format version.
            storage_key: S3-compatible storage key for the archive.
            created_by_run_id: Optional run ID that created this checkpoint.
            previous_checkpoint_id: Optional previous checkpoint for fallback chain.
            manifest_json: Optional manifest metadata as JSON.

        Returns:
            The created WorkspaceCheckpoint.
        """
        checkpoint = WorkspaceCheckpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            version=version,
            storage_key=storage_key,
            created_by_run_id=created_by_run_id,
            previous_checkpoint_id=previous_checkpoint_id,
            manifest_json=manifest_json,
            state=CheckpointState.PENDING,
        )

        self._session.add(checkpoint)
        self._session.flush()

        return checkpoint

    def get_by_id(self, checkpoint_db_id: UUID) -> Optional[WorkspaceCheckpoint]:
        """Get checkpoint by database ID.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.

        Returns:
            WorkspaceCheckpoint if found, None otherwise.
        """
        stmt = select(WorkspaceCheckpoint).where(
            WorkspaceCheckpoint.id == checkpoint_db_id
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_checkpoint_id(
        self,
        checkpoint_id: str,
    ) -> Optional[WorkspaceCheckpoint]:
        """Get checkpoint by checkpoint_id string.

        Args:
            checkpoint_id: Unique checkpoint identifier.

        Returns:
            WorkspaceCheckpoint if found, None otherwise.
        """
        stmt = select(WorkspaceCheckpoint).where(
            WorkspaceCheckpoint.checkpoint_id == checkpoint_id
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_checkpoint_id_and_workspace(
        self,
        checkpoint_id: str,
        workspace_id: UUID,
    ) -> Optional[WorkspaceCheckpoint]:
        """Get checkpoint by checkpoint_id with workspace verification.

        Args:
            checkpoint_id: Unique checkpoint identifier.
            workspace_id: UUID of the workspace.

        Returns:
            WorkspaceCheckpoint if found and belongs to workspace, None otherwise.
        """
        stmt = select(WorkspaceCheckpoint).where(
            and_(
                WorkspaceCheckpoint.checkpoint_id == checkpoint_id,
                WorkspaceCheckpoint.workspace_id == workspace_id,
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        state: Optional[CheckpointState] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkspaceCheckpoint]:
        """List checkpoints for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            state: Optional state filter.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of WorkspaceCheckpoint records in reverse chronological order.
        """
        stmt = select(WorkspaceCheckpoint).where(
            WorkspaceCheckpoint.workspace_id == workspace_id
        )

        if state:
            stmt = stmt.where(WorkspaceCheckpoint.state == state)

        stmt = stmt.order_by(desc(WorkspaceCheckpoint.created_at))
        stmt = stmt.limit(limit).offset(offset)

        return list(self._session.execute(stmt).scalars().all())

    def list_completed_by_workspace(
        self,
        workspace_id: UUID,
        limit: int = 100,
    ) -> List[WorkspaceCheckpoint]:
        """List completed checkpoints for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            limit: Maximum number of results.

        Returns:
            List of completed WorkspaceCheckpoint records.
        """
        return self.list_by_workspace(
            workspace_id=workspace_id,
            state=CheckpointState.COMPLETED,
            limit=limit,
        )

    def get_active_checkpoint(
        self,
        workspace_id: UUID,
    ) -> Optional[WorkspaceCheckpoint]:
        """Get the currently active checkpoint for a workspace.

        Uses the workspace_active_checkpoints table to find the
        checkpoint currently marked as active.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Active WorkspaceCheckpoint if set, None otherwise.
        """
        # Get the active checkpoint pointer
        active_pointer_stmt = select(WorkspaceActiveCheckpoint).where(
            WorkspaceActiveCheckpoint.workspace_id == workspace_id
        )
        active_pointer = self._session.execute(active_pointer_stmt).scalar_one_or_none()

        if not active_pointer:
            return None

        # Get the actual checkpoint record
        return self.get_by_id(active_pointer.checkpoint_id)

    def get_active_checkpoint_id(
        self,
        workspace_id: UUID,
    ) -> Optional[UUID]:
        """Get the ID of the currently active checkpoint.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            UUID of active checkpoint if set, None otherwise.
        """
        active_checkpoint = self.get_active_checkpoint(workspace_id)
        return active_checkpoint.id if active_checkpoint else None

    def set_active_checkpoint(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
        changed_by: Optional[str] = None,
        changed_reason: Optional[str] = None,
    ) -> WorkspaceActiveCheckpoint:
        """Set the active checkpoint for a workspace.

        Creates or updates the active checkpoint pointer.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: UUID of the checkpoint to set as active.
            changed_by: Optional identifier of who/what changed the pointer.
            changed_reason: Optional reason for the change.

        Returns:
            The WorkspaceActiveCheckpoint record.
        """
        # Check if an active checkpoint record already exists
        stmt = select(WorkspaceActiveCheckpoint).where(
            WorkspaceActiveCheckpoint.workspace_id == workspace_id
        )
        active_pointer = self._session.execute(stmt).scalar_one_or_none()

        if active_pointer:
            # Update existing
            active_pointer.checkpoint_id = checkpoint_id
            active_pointer.changed_by = changed_by
            active_pointer.changed_reason = changed_reason
        else:
            # Create new
            active_pointer = WorkspaceActiveCheckpoint(
                workspace_id=workspace_id,
                checkpoint_id=checkpoint_id,
                changed_by=changed_by,
                changed_reason=changed_reason,
            )
            self._session.add(active_pointer)

        self._session.flush()

        return active_pointer

    def advance_active_checkpoint(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
        changed_by: Optional[str] = None,
    ) -> WorkspaceActiveCheckpoint:
        """Auto-advance the active checkpoint pointer to a new checkpoint.

        This is called when a checkpoint completes successfully.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: UUID of the completed checkpoint.
            changed_by: Optional identifier of who/what changed the pointer.

        Returns:
            The updated WorkspaceActiveCheckpoint record.
        """
        return self.set_active_checkpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            changed_by=changed_by or "auto_advance_on_completion",
            changed_reason="Checkpoint completed successfully",
        )

    def update_state(
        self,
        checkpoint_db_id: UUID,
        state: CheckpointState,
        storage_size_bytes: Optional[int] = None,
    ) -> Optional[WorkspaceCheckpoint]:
        """Update checkpoint state.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.
            state: New state value.
            storage_size_bytes: Optional storage size in bytes.

        Returns:
            Updated WorkspaceCheckpoint if found, None otherwise.
        """
        checkpoint = self.get_by_id(checkpoint_db_id)
        if not checkpoint:
            return None

        checkpoint.state = state

        if state == CheckpointState.COMPLETED:
            checkpoint.completed_at = datetime.utcnow()
        elif state == CheckpointState.IN_PROGRESS:
            checkpoint.started_at = datetime.utcnow()

        if storage_size_bytes is not None:
            checkpoint.storage_size_bytes = storage_size_bytes

        self._session.flush()

        return checkpoint

    def mark_in_progress(
        self,
        checkpoint_db_id: UUID,
    ) -> Optional[WorkspaceCheckpoint]:
        """Mark checkpoint as in progress.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.

        Returns:
            Updated WorkspaceCheckpoint if found, None otherwise.
        """
        return self.update_state(checkpoint_db_id, CheckpointState.IN_PROGRESS)

    def mark_completed(
        self,
        checkpoint_db_id: UUID,
        storage_size_bytes: Optional[int] = None,
    ) -> Optional[WorkspaceCheckpoint]:
        """Mark checkpoint as completed.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.
            storage_size_bytes: Optional storage size in bytes.

        Returns:
            Updated WorkspaceCheckpoint if found, None otherwise.
        """
        return self.update_state(
            checkpoint_db_id,
            CheckpointState.COMPLETED,
            storage_size_bytes=storage_size_bytes,
        )

    def mark_failed(
        self,
        checkpoint_db_id: UUID,
    ) -> Optional[WorkspaceCheckpoint]:
        """Mark checkpoint as failed.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.

        Returns:
            Updated WorkspaceCheckpoint if found, None otherwise.
        """
        return self.update_state(checkpoint_db_id, CheckpointState.FAILED)

    def mark_partial(
        self,
        checkpoint_db_id: UUID,
    ) -> Optional[WorkspaceCheckpoint]:
        """Mark checkpoint as partial.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.

        Returns:
            Updated WorkspaceCheckpoint if found, None otherwise.
        """
        return self.update_state(checkpoint_db_id, CheckpointState.PARTIAL)

    def get_fallback_chain(
        self,
        checkpoint_db_id: UUID,
        max_depth: int = 5,
    ) -> List[WorkspaceCheckpoint]:
        """Traverse the fallback chain for a checkpoint.

        Walks the previous_checkpoint_id links to build a list
        of checkpoints that can be used as fallback for restore.

        Args:
            checkpoint_db_id: Starting checkpoint UUID.
            max_depth: Maximum chain depth to traverse.

        Returns:
            List of WorkspaceCheckpoint records in fallback order.
        """
        chain = []
        current_id = checkpoint_db_id

        for _ in range(max_depth):
            checkpoint = self.get_by_id(current_id)
            if not checkpoint:
                break

            chain.append(checkpoint)

            if not checkpoint.previous_checkpoint_id:
                break

            current_id = checkpoint.previous_checkpoint_id

        return chain

    def get_previous_completed_checkpoint(
        self,
        workspace_id: UUID,
        before: Optional[datetime] = None,
    ) -> Optional[WorkspaceCheckpoint]:
        """Get the most recent completed checkpoint before a given time.

        Args:
            workspace_id: UUID of the workspace.
            before: Optional datetime cutoff (defaults to now).

        Returns:
            Most recent completed WorkspaceCheckpoint if any, None otherwise.
        """
        before = before or datetime.utcnow()

        stmt = (
            select(WorkspaceCheckpoint)
            .where(
                and_(
                    WorkspaceCheckpoint.workspace_id == workspace_id,
                    WorkspaceCheckpoint.state == CheckpointState.COMPLETED,
                    WorkspaceCheckpoint.completed_at < before,
                )
            )
            .order_by(desc(WorkspaceCheckpoint.completed_at))
            .limit(1)
        )

        return self._session.execute(stmt).scalar_one_or_none()
