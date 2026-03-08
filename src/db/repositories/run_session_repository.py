"""Repository for run session operations.

Provides CRUD and query methods for run session lifecycle management.
Links runs to workspaces, checkpoints, and sandboxes for complete execution context.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.models import (
    RunSession,
    RunSessionState,
)


class RunSessionRepository:
    """Repository for run session lifecycle operations."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        workspace_id: UUID,
        run_id: str,
        principal_id: Optional[str] = None,
        principal_type: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        request_payload_json: Optional[str] = None,
        sandbox_id: Optional[UUID] = None,
        checkpoint_id: Optional[UUID] = None,
    ) -> RunSession:
        """Create a new run session.

        Args:
            workspace_id: UUID of the workspace.
            run_id: Unique run identifier.
            principal_id: Optional user ID or guest principal ID.
            principal_type: Optional "user" or "guest".
            parent_run_id: Optional parent run for nested runs.
            request_payload_json: Optional request metadata as JSON.
            sandbox_id: Optional associated sandbox.
            checkpoint_id: Optional restored checkpoint.

        Returns:
            The created RunSession.
        """
        run_session = RunSession(
            workspace_id=workspace_id,
            run_id=run_id,
            principal_id=principal_id,
            principal_type=principal_type,
            parent_run_id=parent_run_id,
            request_payload_json=request_payload_json,
            sandbox_id=sandbox_id,
            checkpoint_id=checkpoint_id,
            state=RunSessionState.QUEUED,
            started_at=datetime.utcnow(),
        )

        self._session.add(run_session)
        self._session.flush()

        return run_session

    def get_by_id(self, session_id: UUID) -> Optional[RunSession]:
        """Get run session by ID.

        Args:
            session_id: UUID of the run session.

        Returns:
            RunSession if found, None otherwise.
        """
        stmt = select(RunSession).where(RunSession.id == session_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_run_id(self, run_id: str) -> Optional[RunSession]:
        """Get run session by run_id.

        Args:
            run_id: Unique run identifier.

        Returns:
            RunSession if found, None otherwise.
        """
        stmt = select(RunSession).where(RunSession.run_id == run_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_run_id_and_workspace(
        self,
        run_id: str,
        workspace_id: UUID,
    ) -> Optional[RunSession]:
        """Get run session by run_id with workspace verification.

        Args:
            run_id: Unique run identifier.
            workspace_id: UUID of the workspace.

        Returns:
            RunSession if found and belongs to workspace, None otherwise.
        """
        stmt = select(RunSession).where(
            and_(
                RunSession.run_id == run_id,
                RunSession.workspace_id == workspace_id,
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        state: Optional[RunSessionState] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RunSession]:
        """List run sessions for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            state: Optional state filter.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of RunSession records.
        """
        stmt = select(RunSession).where(RunSession.workspace_id == workspace_id)

        if state:
            stmt = stmt.where(RunSession.state == state)

        stmt = stmt.order_by(RunSession.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        return list(self._session.execute(stmt).scalars().all())

    def list_active_by_workspace(
        self,
        workspace_id: UUID,
    ) -> List[RunSession]:
        """List active (queued or running) run sessions for a workspace.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            List of active RunSession records.
        """
        stmt = select(RunSession).where(
            and_(
                RunSession.workspace_id == workspace_id,
                RunSession.state.in_(
                    [
                        RunSessionState.QUEUED,
                        RunSessionState.RUNNING,
                        RunSessionState.PAUSED,
                    ]
                ),
            )
        )
        stmt = stmt.order_by(RunSession.created_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def update_state(
        self,
        session_id: UUID,
        state: RunSessionState,
    ) -> Optional[RunSession]:
        """Update run session state.

        Args:
            session_id: UUID of the run session.
            state: New state value.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        run_session.state = state
        self._session.flush()

        return run_session

    def mark_running(
        self,
        session_id: UUID,
    ) -> Optional[RunSession]:
        """Mark run session as running.

        Args:
            session_id: UUID of the run session.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        run_session.state = RunSessionState.RUNNING
        self._session.flush()

        return run_session

    def mark_completed(
        self,
        session_id: UUID,
        result_payload_json: Optional[str] = None,
    ) -> Optional[RunSession]:
        """Mark run session as completed.

        Args:
            session_id: UUID of the run session.
            result_payload_json: Optional result metadata as JSON.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        now = datetime.utcnow()
        run_session.state = RunSessionState.COMPLETED
        run_session.completed_at = now

        if run_session.started_at:
            run_session.duration_ms = int((now - run_session.started_at).total_seconds() * 1000)

        if result_payload_json:
            run_session.result_payload_json = result_payload_json

        self._session.flush()

        return run_session

    def mark_failed(
        self,
        session_id: UUID,
        error_message: str,
        error_code: Optional[str] = None,
    ) -> Optional[RunSession]:
        """Mark run session as failed.

        Args:
            session_id: UUID of the run session.
            error_message: Error description.
            error_code: Optional error code for categorization.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        now = datetime.utcnow()
        run_session.state = RunSessionState.FAILED
        run_session.completed_at = now
        run_session.error_message = error_message
        run_session.error_code = error_code

        if run_session.started_at:
            run_session.duration_ms = int((now - run_session.started_at).total_seconds() * 1000)

        self._session.flush()

        return run_session

    def mark_cancelled(
        self,
        session_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[RunSession]:
        """Mark run session as cancelled.

        Args:
            session_id: UUID of the run session.
            reason: Optional cancellation reason.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        now = datetime.utcnow()
        run_session.state = RunSessionState.CANCELLED
        run_session.completed_at = now

        if run_session.started_at:
            run_session.duration_ms = int((now - run_session.started_at).total_seconds() * 1000)

        if reason:
            run_session.error_message = reason

        self._session.flush()

        return run_session

    def set_sandbox(
        self,
        session_id: UUID,
        sandbox_id: UUID,
    ) -> Optional[RunSession]:
        """Associate a sandbox with the run session.

        Args:
            session_id: UUID of the run session.
            sandbox_id: UUID of the sandbox.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        run_session.sandbox_id = sandbox_id
        self._session.flush()

        return run_session

    def set_checkpoint(
        self,
        session_id: UUID,
        checkpoint_id: UUID,
    ) -> Optional[RunSession]:
        """Associate a checkpoint with the run session.

        Args:
            session_id: UUID of the run session.
            checkpoint_id: UUID of the checkpoint.

        Returns:
            Updated RunSession if found, None otherwise.
        """
        run_session = self.get_by_id(session_id)
        if not run_session:
            return None

        run_session.checkpoint_id = checkpoint_id
        self._session.flush()

        return run_session
