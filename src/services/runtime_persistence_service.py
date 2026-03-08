"""Runtime persistence service for run/session metadata and event logging.

Provides durable persistence for non-guest run executions:
- Run session creation and lifecycle state management
- Runtime event logging (append-only)
- Audit event append-only logging
- Guest mode non-persistence guard
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.db.models import (
    RuntimeEventType,
)
from src.db.repositories.run_session_repository import RunSessionRepository
from src.db.repositories.runtime_event_repository import RuntimeEventRepository
from src.db.repositories.audit_event_repository import AuditEventRepository


class GuestPersistenceError(Exception):
    """Raised when guest mode tries to access persistent storage."""

    pass


class RuntimePersistenceService:
    """Service for persisting run execution metadata and events.

    This service handles durable persistence for non-guest runs:
    - Creates and manages run session records
    - Logs runtime events (lifecycle, checkpoints, policy)
    - Appends audit events for compliance
    - Blocks all persistence operations for guest principals

    Guest runs are explicitly non-persistent by design. All
    persistence methods raise GuestPersistenceError for guests.
    """

    def __init__(
        self,
        session: Session,
        run_repo: Optional[RunSessionRepository] = None,
        event_repo: Optional[RuntimeEventRepository] = None,
        audit_repo: Optional[AuditEventRepository] = None,
    ):
        """Initialize persistence service.

        Args:
            session: Database session for persistence operations.
            run_repo: Optional RunSessionRepository (created if not provided).
            event_repo: Optional RuntimeEventRepository (created if not provided).
            audit_repo: Optional AuditEventRepository (created if not provided).
        """
        self._session = session
        self._run_repo = run_repo or RunSessionRepository(session)
        self._event_repo = event_repo or RuntimeEventRepository(session)
        self._audit_repo = audit_repo or AuditEventRepository(session)

    def create_run_session(
        self,
        workspace_id: UUID,
        run_id: str,
        principal_id: Optional[str] = None,
        principal_type: Optional[str] = None,
        is_guest: bool = False,
        request_payload: Optional[dict[str, Any]] = None,
        sandbox_id: Optional[UUID] = None,
        checkpoint_id: Optional[UUID] = None,
    ) -> Optional[UUID]:
        """Create a run session record.

        Creates a durable run session for non-guest executions.
        Returns None for guest runs (no persistence).

        Args:
            workspace_id: UUID of the workspace.
            run_id: Unique run identifier.
            principal_id: Optional user/principal ID.
            principal_type: Optional "user" or "guest".
            is_guest: Whether this is a guest execution.
            request_payload: Optional request metadata.
            sandbox_id: Optional associated sandbox.
            checkpoint_id: Optional restored checkpoint.

        Returns:
            UUID of created run session, or None for guests.

        Raises:
            GuestPersistenceError: If is_guest=True (guests don't persist).
        """
        # Guest runs are explicitly non-persistent
        if is_guest:
            raise GuestPersistenceError(
                "Guest runs cannot be persisted. "
                "Authenticate with an API key to enable persistence."
            )

        import json

        payload_json = json.dumps(request_payload) if request_payload else None

        run_session = self._run_repo.create(
            workspace_id=workspace_id,
            run_id=run_id,
            principal_id=principal_id,
            principal_type=principal_type,
            request_payload_json=payload_json,
            sandbox_id=sandbox_id,
            checkpoint_id=checkpoint_id,
        )

        # Log run started event
        self._event_repo.log_session_started(
            run_session_id=run_session.id,
            payload_json=payload_json,
            actor_id=principal_id,
        )

        # Audit log
        self._audit_repo.log_run_execution(
            workspace_id=workspace_id,
            run_id=run_id,
            action="created",
            outcome="success",
            actor_id=principal_id,
        )

        return run_session.id

    def mark_run_running(
        self,
        run_session_id: UUID,
        workspace_id: UUID,
        run_id: str,
        principal_id: Optional[str] = None,
        is_guest: bool = False,
    ) -> bool:
        """Mark a run session as running.

        Args:
            run_session_id: UUID of the run session.
            workspace_id: UUID of the workspace (for audit).
            run_id: Run identifier (for audit).
            principal_id: Optional actor ID.
            is_guest: Whether this is a guest execution.

        Returns:
            True if updated successfully.

        Raises:
            GuestPersistenceError: If is_guest=True.
        """
        if is_guest:
            raise GuestPersistenceError("Guest runs cannot update persistent state")

        self._run_repo.mark_running(run_session_id)

        # Log runtime event
        self._event_repo.create(
            run_session_id=run_session_id,
            event_type=RuntimeEventType.SESSION_RESUMED,
            actor_id=principal_id,
        )

        # Audit log
        self._audit_repo.log_run_execution(
            workspace_id=workspace_id,
            run_id=run_id,
            action="started",
            outcome="success",
            actor_id=principal_id,
        )

        return True

    def mark_run_completed(
        self,
        run_session_id: UUID,
        workspace_id: UUID,
        run_id: str,
        result_payload: Optional[dict[str, Any]] = None,
        principal_id: Optional[str] = None,
        is_guest: bool = False,
    ) -> bool:
        """Mark a run session as completed.

        Args:
            run_session_id: UUID of the run session.
            workspace_id: UUID of the workspace (for audit).
            run_id: Run identifier (for audit).
            result_payload: Optional result metadata.
            principal_id: Optional actor ID.
            is_guest: Whether this is a guest execution.

        Returns:
            True if updated successfully.

        Raises:
            GuestPersistenceError: If is_guest=True.
        """
        if is_guest:
            raise GuestPersistenceError("Guest runs cannot update persistent state")

        import json

        result_json = json.dumps(result_payload) if result_payload else None

        self._run_repo.mark_completed(run_session_id, result_payload_json=result_json)

        # Log runtime event
        self._event_repo.log_session_completed(
            run_session_id=run_session_id,
            payload_json=result_json,
            actor_id=principal_id,
        )

        # Audit log
        self._audit_repo.log_run_execution(
            workspace_id=workspace_id,
            run_id=run_id,
            action="completed",
            outcome="success",
            actor_id=principal_id,
            payload_json=result_json,
        )

        return True

    def mark_run_failed(
        self,
        run_session_id: UUID,
        workspace_id: UUID,
        run_id: str,
        error_message: str,
        error_code: Optional[str] = None,
        principal_id: Optional[str] = None,
        is_guest: bool = False,
    ) -> bool:
        """Mark a run session as failed.

        Args:
            run_session_id: UUID of the run session.
            workspace_id: UUID of the workspace (for audit).
            run_id: Run identifier (for audit).
            error_message: Error description.
            error_code: Optional error code.
            principal_id: Optional actor ID.
            is_guest: Whether this is a guest execution.

        Returns:
            True if updated successfully.

        Raises:
            GuestPersistenceError: If is_guest=True.
        """
        if is_guest:
            raise GuestPersistenceError("Guest runs cannot update persistent state")

        self._run_repo.mark_failed(
            run_session_id, error_message=error_message, error_code=error_code
        )

        # Log runtime event
        self._event_repo.log_session_failed(
            run_session_id=run_session_id,
            error_message=error_message,
            error_code=error_code,
            actor_id=principal_id,
        )

        # Audit log
        import json

        self._audit_repo.log_run_execution(
            workspace_id=workspace_id,
            run_id=run_id,
            action="failed",
            outcome="failure",
            actor_id=principal_id,
            reason=error_message,
            payload_json=json.dumps({"error_code": error_code}) if error_code else None,
        )

        return True

    def log_checkpoint_created(
        self,
        run_session_id: UUID,
        workspace_id: UUID,
        checkpoint_id: UUID,
        run_id: str,
        principal_id: Optional[str] = None,
        is_guest: bool = False,
    ) -> bool:
        """Log a checkpoint creation event.

        Args:
            run_session_id: UUID of the run session.
            workspace_id: UUID of the workspace.
            checkpoint_id: UUID of the checkpoint.
            run_id: Run identifier (for audit).
            principal_id: Optional actor ID.
            is_guest: Whether this is a guest execution.

        Returns:
            True if logged successfully.

        Raises:
            GuestPersistenceError: If is_guest=True.
        """
        if is_guest:
            raise GuestPersistenceError("Guest runs cannot create checkpoint events")

        # Log runtime event
        self._event_repo.log_checkpoint_created(
            run_session_id=run_session_id,
            checkpoint_id=checkpoint_id,
            actor_id=principal_id,
        )

        # Audit log
        self._audit_repo.log_checkpoint_management(
            workspace_id=workspace_id,
            checkpoint_id=str(checkpoint_id),
            action="created",
            outcome="success",
            actor_id=principal_id,
        )

        return True

    def log_policy_violation(
        self,
        run_session_id: UUID,
        workspace_id: UUID,
        run_id: str,
        action: str,
        resource: str,
        reason: str,
        principal_id: Optional[str] = None,
        is_guest: bool = False,
    ) -> bool:
        """Log a policy violation event.

        Args:
            run_session_id: UUID of the run session.
            workspace_id: UUID of the workspace.
            run_id: Run identifier.
            action: The denied action.
            resource: The resource being accessed.
            reason: Why the action was denied.
            principal_id: Optional actor ID.
            is_guest: Whether this is a guest execution.

        Returns:
            True if logged successfully (even for guests - this is security).
        """
        # Policy violations are always logged for security
        # We don't block these even for guests

        # Log runtime event
        self._event_repo.log_policy_violation(
            run_session_id=run_session_id,
            action=action,
            resource=resource,
            reason=reason,
            actor_id=principal_id,
        )

        # Audit log
        self._audit_repo.log_policy_enforcement(
            workspace_id=workspace_id,
            resource_type="run",
            resource_id=run_id,
            action=action,
            outcome="denied",
            actor_id=principal_id,
            reason=reason,
        )

        return True

    def get_run_session(self, run_session_id: UUID) -> Optional[dict[str, Any]]:
        """Get run session by ID.

        Args:
            run_session_id: UUID of the run session.

        Returns:
            Run session data as dict if found, None otherwise.
        """
        run_session = self._run_repo.get_by_id(run_session_id)
        if not run_session:
            return None

        return self._serialize_run_session(run_session)

    def get_run_by_run_id(self, run_id: str) -> Optional[dict[str, Any]]:
        """Get run session by run_id.

        Args:
            run_id: Unique run identifier.

        Returns:
            Run session data as dict if found, None otherwise.
        """
        run_session = self._run_repo.get_by_run_id(run_id)
        if not run_session:
            return None

        return self._serialize_run_session(run_session)

    def list_run_events(
        self,
        run_session_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List runtime events for a run session.

        Args:
            run_session_id: UUID of the run session.
            limit: Maximum number of events.

        Returns:
            List of runtime event data as dicts.
        """
        events = self._event_repo.list_by_run_session(run_session_id=run_session_id, limit=limit)
        return [self._serialize_runtime_event(e) for e in events]

    def _serialize_run_session(self, run_session: Any) -> dict[str, Any]:
        """Serialize a RunSession to a dict.

        Args:
            run_session: RunSession model instance.

        Returns:
            Dict representation of the run session.
        """
        # Handle both enum (PostgreSQL) and string (SQLite) states
        state = run_session.state
        if hasattr(state, "value"):
            state = state.value

        return {
            "id": str(run_session.id),
            "workspace_id": str(run_session.workspace_id),
            "run_id": run_session.run_id,
            "parent_run_id": run_session.parent_run_id,
            "state": state,
            "principal_id": run_session.principal_id,
            "principal_type": run_session.principal_type,
            "sandbox_id": str(run_session.sandbox_id) if run_session.sandbox_id else None,
            "checkpoint_id": str(run_session.checkpoint_id) if run_session.checkpoint_id else None,
            "request_payload": run_session.request_payload_json,
            "result_payload": run_session.result_payload_json,
            "error_message": run_session.error_message,
            "error_code": run_session.error_code,
            "started_at": run_session.started_at.isoformat() if run_session.started_at else None,
            "completed_at": run_session.completed_at.isoformat()
            if run_session.completed_at
            else None,
            "duration_ms": run_session.duration_ms,
            "created_at": run_session.created_at.isoformat() if run_session.created_at else None,
        }

    def _serialize_runtime_event(self, event: Any) -> dict[str, Any]:
        """Serialize a RuntimeEvent to a dict.

        Args:
            event: RuntimeEvent model instance.

        Returns:
            Dict representation of the event.
        """
        # Handle both enum (PostgreSQL) and string (SQLite) event types
        event_type = event.event_type
        if hasattr(event_type, "value"):
            event_type = event_type.value

        return {
            "id": str(event.id),
            "run_session_id": str(event.run_session_id),
            "event_type": event_type,
            "actor_id": event.actor_id,
            "actor_type": event.actor_type,
            "payload": event.payload_json,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "correlation_id": event.correlation_id,
        }
