"""Repository for runtime event operations.

Provides CRUD and query methods for runtime event logging.
Events are append-only and immutable once written.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.models import (
    RuntimeEvent,
    RuntimeEventType,
)


class RuntimeEventRepository:
    """Repository for runtime event lifecycle operations."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        run_session_id: UUID,
        event_type: RuntimeEventType,
        payload_json: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Create a new runtime event.

        Args:
            run_session_id: UUID of the associated run session.
            event_type: Type of runtime event.
            payload_json: Optional event payload as JSON.
            actor_id: Optional actor identifier.
            actor_type: Optional actor type.
            correlation_id: Optional correlation ID for distributed tracing.

        Returns:
            The created RuntimeEvent.
        """
        event = RuntimeEvent(
            run_session_id=run_session_id,
            event_type=event_type,
            payload_json=payload_json,
            actor_id=actor_id,
            actor_type=actor_type,
            correlation_id=correlation_id,
            occurred_at=datetime.utcnow(),
        )

        self._session.add(event)
        self._session.flush()

        return event

    def get_by_id(self, event_id: UUID) -> Optional[RuntimeEvent]:
        """Get runtime event by ID.

        Args:
            event_id: UUID of the event.

        Returns:
            RuntimeEvent if found, None otherwise.
        """
        stmt = select(RuntimeEvent).where(RuntimeEvent.id == event_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_run_session(
        self,
        run_session_id: UUID,
        event_type: Optional[RuntimeEventType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RuntimeEvent]:
        """List runtime events for a run session.

        Args:
            run_session_id: UUID of the run session.
            event_type: Optional event type filter.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of RuntimeEvent records in chronological order.
        """
        stmt = select(RuntimeEvent).where(RuntimeEvent.run_session_id == run_session_id)

        if event_type:
            stmt = stmt.where(RuntimeEvent.event_type == event_type)

        stmt = stmt.order_by(RuntimeEvent.occurred_at.asc())
        stmt = stmt.limit(limit).offset(offset)

        return list(self._session.execute(stmt).scalars().all())

    def list_by_run_session_chronological(
        self,
        run_session_id: UUID,
        limit: int = 100,
    ) -> List[RuntimeEvent]:
        """List runtime events for a run session in chronological order.

        Args:
            run_session_id: UUID of the run session.
            limit: Maximum number of results.

        Returns:
            List of RuntimeEvent records in chronological order.
        """
        return self.list_by_run_session(
            run_session_id=run_session_id,
            limit=limit,
        )

    def list_by_workspace(
        self,
        workspace_id: UUID,
        event_type: Optional[RuntimeEventType] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RuntimeEvent]:
        """List runtime events for a workspace.

        Requires joining with run_sessions table for workspace filtering.

        Args:
            workspace_id: UUID of the workspace.
            event_type: Optional event type filter.
            since: Optional start time filter.
            until: Optional end time filter.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of RuntimeEvent records.
        """
        from src.db.models import RunSession

        stmt = (
            select(RuntimeEvent)
            .join(RunSession, RuntimeEvent.run_session_id == RunSession.id)
            .where(RunSession.workspace_id == workspace_id)
        )

        if event_type:
            stmt = stmt.where(RuntimeEvent.event_type == event_type)

        if since:
            stmt = stmt.where(RuntimeEvent.occurred_at >= since)

        if until:
            stmt = stmt.where(RuntimeEvent.occurred_at <= until)

        stmt = stmt.order_by(RuntimeEvent.occurred_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        return list(self._session.execute(stmt).scalars().all())

    def count_by_run_session(
        self,
        run_session_id: UUID,
        event_type: Optional[RuntimeEventType] = None,
    ) -> int:
        """Count runtime events for a run session.

        Args:
            run_session_id: UUID of the run session.
            event_type: Optional event type filter.

        Returns:
            Count of matching events.
        """
        from sqlalchemy import func

        stmt = select(func.count(RuntimeEvent.id)).where(
            RuntimeEvent.run_session_id == run_session_id
        )

        if event_type:
            stmt = stmt.where(RuntimeEvent.event_type == event_type)

        return self._session.execute(stmt).scalar() or 0

    def list_by_correlation_id(
        self,
        correlation_id: str,
        limit: int = 100,
    ) -> List[RuntimeEvent]:
        """List runtime events by correlation ID.

        Args:
            correlation_id: Correlation ID for distributed tracing.
            limit: Maximum number of results.

        Returns:
            List of RuntimeEvent records.
        """
        stmt = select(RuntimeEvent).where(RuntimeEvent.correlation_id == correlation_id)
        stmt = stmt.order_by(RuntimeEvent.occurred_at.asc())
        stmt = stmt.limit(limit)

        return list(self._session.execute(stmt).scalars().all())

    # Convenience methods for common event types

    def log_session_started(
        self,
        run_session_id: UUID,
        payload_json: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Log a session started event.

        Args:
            run_session_id: UUID of the run session.
            payload_json: Optional event payload as JSON.
            actor_id: Optional actor identifier.

        Returns:
            The created RuntimeEvent.
        """
        return self.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.SESSION_STARTED,
            payload_json=payload_json,
            actor_id=actor_id,
        )

    def log_session_completed(
        self,
        run_session_id: UUID,
        payload_json: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Log a session completed event.

        Args:
            run_session_id: UUID of the run session.
            payload_json: Optional event payload as JSON.
            actor_id: Optional actor identifier.

        Returns:
            The created RuntimeEvent.
        """
        return self.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.SESSION_COMPLETED,
            payload_json=payload_json,
            actor_id=actor_id,
        )

    def log_session_failed(
        self,
        run_session_id: UUID,
        error_message: str,
        error_code: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Log a session failed event.

        Args:
            run_session_id: UUID of the run session.
            error_message: Error description.
            error_code: Optional error code.
            actor_id: Optional actor identifier.

        Returns:
            The created RuntimeEvent.
        """
        import json

        payload = {"error_message": error_message}
        if error_code:
            payload["error_code"] = error_code

        return self.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.SESSION_FAILED,
            payload_json=json.dumps(payload),
            actor_id=actor_id,
        )

    def log_checkpoint_created(
        self,
        run_session_id: UUID,
        checkpoint_id: UUID,
        actor_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Log a checkpoint created event.

        Args:
            run_session_id: UUID of the run session.
            checkpoint_id: UUID of the checkpoint.
            actor_id: Optional actor identifier.

        Returns:
            The created RuntimeEvent.
        """
        import json

        return self.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.CHECKPOINT_CREATED,
            payload_json=json.dumps({"checkpoint_id": str(checkpoint_id)}),
            actor_id=actor_id,
        )

    def log_policy_violation(
        self,
        run_session_id: UUID,
        action: str,
        resource: str,
        reason: str,
        actor_id: Optional[str] = None,
    ) -> RuntimeEvent:
        """Log a policy violation event.

        Args:
            run_session_id: UUID of the run session.
            action: The action that was denied.
            resource: The resource being accessed.
            reason: Why the action was denied.
            actor_id: Optional actor identifier.

        Returns:
            The created RuntimeEvent.
        """
        import json

        payload = {
            "action": action,
            "resource": resource,
            "reason": reason,
        }

        return self.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.POLICY_VIOLATION,
            payload_json=json.dumps(payload),
            actor_id=actor_id,
        )
