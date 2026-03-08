"""Repository for audit event operations.

Provides append-only insert methods for audit event logging.
Audit events are immutable - updates and deletes are rejected.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.models import (
    AuditEvent,
    AuditEventCategory,
)


class AuditEventRepository:
    """Repository for audit event operations.

    This repository only supports CREATE and READ operations.
    UPDATE and DELETE are not exposed to maintain immutability.
    Database-level triggers prevent mutation attempts.
    """

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        category: AuditEventCategory,
        action: str,
        outcome: str,
        resource_type: str,
        resource_id: str,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        payload_json: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AuditEvent:
        """Create a new audit event.

        Args:
            category: Event category for classification.
            action: The action that was performed.
            outcome: Result of the action ("success", "failure", "denied").
            resource_type: Type of resource affected.
            resource_id: Identifier of the affected resource.
            actor_id: Optional actor identifier.
            actor_type: Optional actor type.
            workspace_id: Optional workspace for tenant isolation.
            payload_json: Optional detailed payload as JSON.
            reason: Optional reason or additional context.

        Returns:
            The created AuditEvent.
        """
        event = AuditEvent(
            category=category,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            actor_type=actor_type,
            workspace_id=workspace_id,
            payload_json=payload_json,
            reason=reason,
            occurred_at=datetime.utcnow(),
            immutable=True,
        )

        self._session.add(event)
        self._session.flush()

        return event

    def get_by_id(self, event_id: UUID) -> Optional[AuditEvent]:
        """Get audit event by ID.

        Args:
            event_id: UUID of the audit event.

        Returns:
            AuditEvent if found, None otherwise.
        """
        stmt = select(AuditEvent).where(AuditEvent.id == event_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        category: Optional[AuditEventCategory] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """List audit events for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            category: Optional category filter.
            since: Optional start time filter.
            until: Optional end time filter.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of AuditEvent records in reverse chronological order.
        """
        stmt = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)

        if category:
            stmt = stmt.where(AuditEvent.category == category)

        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)

        if until:
            stmt = stmt.where(AuditEvent.occurred_at <= until)

        stmt = stmt.order_by(AuditEvent.occurred_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        return list(self._session.execute(stmt).scalars().all())

    def list_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """List audit events for a specific resource.

        Args:
            resource_type: Type of resource.
            resource_id: Resource identifier.
            limit: Maximum number of results.

        Returns:
            List of AuditEvent records in reverse chronological order.
        """
        stmt = select(AuditEvent).where(
            and_(
                AuditEvent.resource_type == resource_type,
                AuditEvent.resource_id == resource_id,
            )
        )
        stmt = stmt.order_by(AuditEvent.occurred_at.desc())
        stmt = stmt.limit(limit)

        return list(self._session.execute(stmt).scalars().all())

    def list_by_actor(
        self,
        actor_id: str,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """List audit events by actor.

        Args:
            actor_id: Actor identifier.
            since: Optional start time filter.
            limit: Maximum number of results.

        Returns:
            List of AuditEvent records in reverse chronological order.
        """
        stmt = select(AuditEvent).where(AuditEvent.actor_id == actor_id)

        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)

        stmt = stmt.order_by(AuditEvent.occurred_at.desc())
        stmt = stmt.limit(limit)

        return list(self._session.execute(stmt).scalars().all())

    def list_by_category(
        self,
        category: AuditEventCategory,
        workspace_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """List audit events by category.

        Args:
            category: Event category.
            workspace_id: Optional workspace filter.
            limit: Maximum number of results.

        Returns:
            List of AuditEvent records in reverse chronological order.
        """
        stmt = select(AuditEvent).where(AuditEvent.category == category)

        if workspace_id:
            stmt = stmt.where(AuditEvent.workspace_id == workspace_id)

        stmt = stmt.order_by(AuditEvent.occurred_at.desc())
        stmt = stmt.limit(limit)

        return list(self._session.execute(stmt).scalars().all())

    def count_by_workspace(
        self,
        workspace_id: UUID,
        category: Optional[AuditEventCategory] = None,
        since: Optional[datetime] = None,
    ) -> int:
        """Count audit events for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            category: Optional category filter.
            since: Optional start time filter.

        Returns:
            Count of matching events.
        """
        from sqlalchemy import func

        stmt = select(func.count(AuditEvent.id)).where(AuditEvent.workspace_id == workspace_id)

        if category:
            stmt = stmt.where(AuditEvent.category == category)

        if since:
            stmt = stmt.where(AuditEvent.occurred_at >= since)

        return self._session.execute(stmt).scalar() or 0

    # Convenience methods for common audit events

    def log_run_execution(
        self,
        workspace_id: UUID,
        run_id: str,
        action: str,
        outcome: str,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
        payload_json: Optional[str] = None,
    ) -> AuditEvent:
        """Log a run execution audit event.

        Args:
            workspace_id: UUID of the workspace.
            run_id: Run identifier.
            action: Action performed (e.g., "started", "completed").
            outcome: Result ("success", "failure", "denied").
            actor_id: Optional actor identifier.
            reason: Optional reason or context.
            payload_json: Optional detailed payload.

        Returns:
            The created AuditEvent.
        """
        return self.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action=action,
            outcome=outcome,
            resource_type="run",
            resource_id=run_id,
            actor_id=actor_id,
            workspace_id=workspace_id,
            payload_json=payload_json,
            reason=reason,
        )

    def log_checkpoint_management(
        self,
        workspace_id: UUID,
        checkpoint_id: str,
        action: str,
        outcome: str,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
        payload_json: Optional[str] = None,
    ) -> AuditEvent:
        """Log a checkpoint management audit event.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: Checkpoint identifier.
            action: Action performed (e.g., "created", "restored").
            outcome: Result ("success", "failure", "denied").
            actor_id: Optional actor identifier.
            reason: Optional reason or context.
            payload_json: Optional detailed payload.

        Returns:
            The created AuditEvent.
        """
        return self.create(
            category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
            action=action,
            outcome=outcome,
            resource_type="checkpoint",
            resource_id=checkpoint_id,
            actor_id=actor_id,
            workspace_id=workspace_id,
            payload_json=payload_json,
            reason=reason,
        )

    def log_policy_enforcement(
        self,
        workspace_id: Optional[UUID],
        resource_type: str,
        resource_id: str,
        action: str,
        outcome: str,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
        payload_json: Optional[str] = None,
    ) -> AuditEvent:
        """Log a policy enforcement audit event.

        Args:
            workspace_id: Optional UUID of the workspace.
            resource_type: Type of resource affected.
            resource_id: Resource identifier.
            action: Action that was attempted.
            outcome: Result ("success", "failure", "denied").
            actor_id: Optional actor identifier.
            reason: Optional reason or context.
            payload_json: Optional detailed payload.

        Returns:
            The created AuditEvent.
        """
        return self.create(
            category=AuditEventCategory.POLICY_ENFORCEMENT,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            workspace_id=workspace_id,
            payload_json=payload_json,
            reason=reason,
        )

    def log_system_operation(
        self,
        action: str,
        outcome: str,
        resource_type: str,
        resource_id: str,
        actor_id: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        payload_json: Optional[str] = None,
    ) -> AuditEvent:
        """Log a system operation audit event.

        Args:
            action: System action performed.
            outcome: Result ("success", "failure").
            resource_type: Type of resource affected.
            resource_id: Resource identifier.
            actor_id: Optional actor identifier (system component).
            workspace_id: Optional workspace context.
            reason: Optional reason or context.
            payload_json: Optional detailed payload.

        Returns:
            The created AuditEvent.
        """
        return self.create(
            category=AuditEventCategory.SYSTEM_OPERATION,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            workspace_id=workspace_id,
            payload_json=payload_json,
            reason=reason,
        )
