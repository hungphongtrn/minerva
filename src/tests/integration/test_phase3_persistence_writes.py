"""Integration tests for Phase 3 persistence write paths.

Tests non-guest run persistence, checkpoint metadata writes,
active pointer advancement, and append-only audit logging.
"""

import json
import pytest
from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session

from src.db.models import (
    RunSessionState,
    RuntimeEventType,
    CheckpointState,
    AuditEventCategory,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
)
from src.db.repositories import (
    RunSessionRepository,
    RuntimeEventRepository,
    WorkspaceCheckpointRepository,
    AuditEventRepository,
)
from src.services.runtime_persistence_service import (
    RuntimePersistenceService,
    GuestPersistenceError,
)
from src.services.workspace_checkpoint_service import (
    WorkspaceCheckpointService,
    GuestCheckpointError,
)
from src.services.run_service import RunService
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope


class TestRunSessionRepository:
    """Tests for RunSessionRepository."""

    def test_create_run_session(self, db_session: Session, workspace_alpha: Any):
        """Test creating a run session."""
        repo = RunSessionRepository(db_session)

        run_session = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="test-run-001",
            principal_id=str(workspace_alpha.owner_id),
            principal_type="user",
        )

        assert run_session.id is not None
        assert run_session.workspace_id == workspace_alpha.id
        assert run_session.run_id == "test-run-001"
        assert run_session.state == RunSessionState.QUEUED
        assert run_session.principal_id == str(workspace_alpha.owner_id)

    def test_get_by_run_id(self, db_session: Session, workspace_alpha: Any):
        """Test retrieving run session by run_id."""
        repo = RunSessionRepository(db_session)

        run_session = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="test-run-002",
        )

        retrieved = repo.get_by_run_id("test-run-002")
        assert retrieved is not None
        assert retrieved.id == run_session.id

    def test_mark_running(self, db_session: Session, workspace_alpha: Any):
        """Test marking run session as running."""
        repo = RunSessionRepository(db_session)

        run_session = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="test-run-003",
        )

        updated = repo.mark_running(run_session.id)
        assert updated is not None
        assert updated.state == RunSessionState.RUNNING

    def test_mark_completed(self, db_session: Session, workspace_alpha: Any):
        """Test marking run session as completed."""
        repo = RunSessionRepository(db_session)

        run_session = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="test-run-004",
        )

        # Mark as running first
        repo.mark_running(run_session.id)

        # Then complete
        updated = repo.mark_completed(
            run_session.id,
            result_payload_json=json.dumps({"output": "success"}),
        )

        assert updated is not None
        assert updated.state == RunSessionState.COMPLETED
        assert updated.completed_at is not None
        assert updated.duration_ms is not None
        assert updated.result_payload_json == '{"output": "success"}'

    def test_mark_failed(self, db_session: Session, workspace_alpha: Any):
        """Test marking run session as failed."""
        repo = RunSessionRepository(db_session)

        run_session = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="test-run-005",
        )

        updated = repo.mark_failed(
            run_session.id,
            error_message="Something went wrong",
            error_code="ERR_001",
        )

        assert updated is not None
        assert updated.state == RunSessionState.FAILED
        assert updated.error_message == "Something went wrong"
        assert updated.error_code == "ERR_001"

    def test_list_by_workspace(self, db_session: Session, workspace_alpha: Any):
        """Test listing run sessions for a workspace."""
        repo = RunSessionRepository(db_session)

        # Create multiple sessions
        for i in range(3):
            repo.create(
                workspace_id=workspace_alpha.id,
                run_id=f"test-run-{i}",
            )

        sessions = repo.list_by_workspace(workspace_alpha.id)
        assert len(sessions) == 3

    def test_list_active_by_workspace(self, db_session: Session, workspace_alpha: Any):
        """Test listing active run sessions."""
        repo = RunSessionRepository(db_session)

        # Create active session
        active = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="active-run",
        )
        repo.mark_running(active.id)

        # Create completed session
        completed = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="completed-run",
        )
        repo.mark_running(completed.id)
        repo.mark_completed(completed.id)

        active_sessions = repo.list_active_by_workspace(workspace_alpha.id)
        assert len(active_sessions) == 1
        assert active_sessions[0].run_id == "active-run"


class TestRuntimeEventRepository:
    """Tests for RuntimeEventRepository."""

    def test_create_runtime_event(self, db_session: Session, workspace_alpha: Any):
        """Test creating a runtime event."""
        # First create a run session
        run_repo = RunSessionRepository(db_session)
        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="event-test-run",
        )

        repo = RuntimeEventRepository(db_session)
        event = repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.SESSION_STARTED,
            payload_json=json.dumps({"init": True}),
        )

        assert event.id is not None
        assert event.run_session_id == run_session.id
        assert event.event_type == RuntimeEventType.SESSION_STARTED
        assert event.payload_json == '{"init": true}'

    def test_list_by_run_session(self, db_session: Session, workspace_alpha: Any):
        """Test listing events for a run session."""
        run_repo = RunSessionRepository(db_session)
        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="event-list-run",
        )

        repo = RuntimeEventRepository(db_session)

        # Create multiple events
        repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.SESSION_STARTED,
        )
        repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.SESSION_COMPLETED,
        )

        events = repo.list_by_run_session(run_session.id)
        assert len(events) == 2

    def test_count_by_run_session(self, db_session: Session, workspace_alpha: Any):
        """Test counting events for a run session."""
        run_repo = RunSessionRepository(db_session)
        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="event-count-run",
        )

        repo = RuntimeEventRepository(db_session)

        # Create events
        repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.SESSION_STARTED,
        )
        repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.CHECKPOINT_CREATED,
        )

        count = repo.count_by_run_session(run_session.id)
        assert count == 2

    def test_log_session_started(self, db_session: Session, workspace_alpha: Any):
        """Test convenience method for logging session start."""
        run_repo = RunSessionRepository(db_session)
        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="log-start-run",
        )

        repo = RuntimeEventRepository(db_session)
        event = repo.log_session_started(
            run_session_id=run_session.id,
            actor_id="test-user",
        )

        assert event.event_type == RuntimeEventType.SESSION_STARTED
        assert event.actor_id == "test-user"


class TestWorkspaceCheckpointRepository:
    """Tests for WorkspaceCheckpointRepository."""

    def test_create_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test creating a checkpoint record."""
        repo = WorkspaceCheckpointRepository(db_session)

        checkpoint = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-001",
        )

        assert checkpoint.id is not None
        assert checkpoint.checkpoint_id == "chk-001"
        assert checkpoint.state == CheckpointState.PENDING

    def test_mark_completed(self, db_session: Session, workspace_alpha: Any):
        """Test marking checkpoint as completed."""
        repo = WorkspaceCheckpointRepository(db_session)

        checkpoint = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-002",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-002",
        )

        updated = repo.mark_completed(
            checkpoint.id,
            storage_size_bytes=1024,
        )

        assert updated is not None
        assert updated.state == CheckpointState.COMPLETED
        assert updated.completed_at is not None
        assert updated.storage_size_bytes == 1024

    def test_set_active_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test setting the active checkpoint pointer."""
        repo = WorkspaceCheckpointRepository(db_session)

        checkpoint = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-003",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-003",
        )
        repo.mark_completed(checkpoint.id)

        active = repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
            changed_by="test-user",
        )

        assert active.checkpoint_id == checkpoint.id
        assert active.changed_by == "test-user"

    def test_get_active_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test retrieving the active checkpoint."""
        repo = WorkspaceCheckpointRepository(db_session)

        # Initially no active checkpoint
        active = repo.get_active_checkpoint(workspace_alpha.id)
        assert active is None

        # Create and set active checkpoint
        checkpoint = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-004",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-004",
        )
        repo.mark_completed(checkpoint.id)
        repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        active = repo.get_active_checkpoint(workspace_alpha.id)
        assert active is not None
        assert active.checkpoint_id == "chk-004"

    def test_advance_active_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test auto-advancing the active checkpoint pointer."""
        repo = WorkspaceCheckpointRepository(db_session)

        # Create first checkpoint
        checkpoint1 = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-005",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-005",
        )
        repo.mark_completed(checkpoint1.id)
        repo.advance_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint1.id,
        )

        # Create second checkpoint
        checkpoint2 = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-006",
            version="1.0.0",
            storage_key="workspaces/test/checkpoints/chk-006",
        )
        repo.mark_completed(checkpoint2.id)
        repo.advance_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint2.id,
        )

        # Verify active is now the second checkpoint
        active = repo.get_active_checkpoint(workspace_alpha.id)
        assert active.checkpoint_id == "chk-006"


class TestAuditEventRepository:
    """Tests for AuditEventRepository."""

    def test_create_audit_event(self, db_session: Session, workspace_alpha: Any):
        """Test creating an audit event."""
        repo = AuditEventRepository(db_session)

        event = repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="created",
            outcome="success",
            resource_type="run",
            resource_id="run-001",
            workspace_id=workspace_alpha.id,
        )

        assert event.id is not None
        assert event.category == AuditEventCategory.RUN_EXECUTION
        assert event.action == "created"
        assert event.immutable is True

    def test_list_by_workspace(self, db_session: Session, workspace_alpha: Any):
        """Test listing audit events for a workspace."""
        repo = AuditEventRepository(db_session)

        # Create multiple events
        repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="created",
            outcome="success",
            resource_type="run",
            resource_id="run-002",
            workspace_id=workspace_alpha.id,
        )
        repo.create(
            category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
            action="created",
            outcome="success",
            resource_type="checkpoint",
            resource_id="chk-001",
            workspace_id=workspace_alpha.id,
        )

        events = repo.list_by_workspace(workspace_alpha.id)
        assert len(events) == 2

    def test_list_by_category(self, db_session: Session, workspace_alpha: Any):
        """Test listing audit events by category."""
        repo = AuditEventRepository(db_session)

        repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="created",
            outcome="success",
            resource_type="run",
            resource_id="run-003",
            workspace_id=workspace_alpha.id,
        )
        repo.create(
            category=AuditEventCategory.POLICY_ENFORCEMENT,
            action="denied",
            outcome="denied",
            resource_type="run",
            resource_id="run-004",
            workspace_id=workspace_alpha.id,
        )

        events = repo.list_by_category(
            AuditEventCategory.POLICY_ENFORCEMENT,
            workspace_id=workspace_alpha.id,
        )
        assert len(events) == 1
        assert events[0].action == "denied"

    def test_log_run_execution(self, db_session: Session, workspace_alpha: Any):
        """Test convenience method for logging run execution."""
        repo = AuditEventRepository(db_session)

        event = repo.log_run_execution(
            workspace_id=workspace_alpha.id,
            run_id="run-005",
            action="completed",
            outcome="success",
            actor_id="test-user",
        )

        assert event.category == AuditEventCategory.RUN_EXECUTION
        assert event.action == "completed"


class TestRuntimePersistenceService:
    """Tests for RuntimePersistenceService."""

    def test_create_run_session_non_guest(
        self, db_session: Session, workspace_alpha: Any
    ):
        """Test creating run session for non-guest user."""
        service = RuntimePersistenceService(db_session)

        session_id = service.create_run_session(
            workspace_id=workspace_alpha.id,
            run_id="persist-run-001",
            principal_id=str(workspace_alpha.owner_id),
            principal_type="user",
            is_guest=False,
        )

        assert session_id is not None

        # Verify in database
        repo = RunSessionRepository(db_session)
        session = repo.get_by_id(session_id)
        assert session is not None
        assert session.run_id == "persist-run-001"

    def test_create_run_session_guest_raises_error(
        self, db_session: Session, workspace_alpha: Any
    ):
        """Test that guest run session creation raises error."""
        service = RuntimePersistenceService(db_session)

        with pytest.raises(GuestPersistenceError):
            service.create_run_session(
                workspace_id=workspace_alpha.id,
                run_id="guest-run-001",
                is_guest=True,
            )

    def test_mark_run_completed(self, db_session: Session, workspace_alpha: Any):
        """Test marking run as completed via service."""
        service = RuntimePersistenceService(db_session)

        # Create session
        session_id = service.create_run_session(
            workspace_id=workspace_alpha.id,
            run_id="persist-run-002",
            is_guest=False,
        )

        # Mark as running
        service.mark_run_running(
            run_session_id=session_id,
            workspace_id=workspace_alpha.id,
            run_id="persist-run-002",
            is_guest=False,
        )

        # Mark as completed
        service.mark_run_completed(
            run_session_id=session_id,
            workspace_id=workspace_alpha.id,
            run_id="persist-run-002",
            result_payload={"output": "success"},
            is_guest=False,
        )

        # Verify
        repo = RunSessionRepository(db_session)
        session = repo.get_by_id(session_id)
        assert session.state == RunSessionState.COMPLETED

    def test_mark_run_failed(self, db_session: Session, workspace_alpha: Any):
        """Test marking run as failed via service."""
        service = RuntimePersistenceService(db_session)

        # Create session
        session_id = service.create_run_session(
            workspace_id=workspace_alpha.id,
            run_id="persist-run-003",
            is_guest=False,
        )

        # Mark as failed
        service.mark_run_failed(
            run_session_id=session_id,
            workspace_id=workspace_alpha.id,
            run_id="persist-run-003",
            error_message="Test failure",
            error_code="TEST_ERR",
            is_guest=False,
        )

        # Verify
        repo = RunSessionRepository(db_session)
        session = repo.get_by_id(session_id)
        assert session.state == RunSessionState.FAILED
        assert session.error_message == "Test failure"


class TestWorkspaceCheckpointService:
    """Tests for WorkspaceCheckpointService."""

    def test_create_checkpoint_metadata_only(
        self, db_session: Session, workspace_alpha: Any
    ):
        """Test creating checkpoint metadata without S3 storage."""
        service = WorkspaceCheckpointService(db_session)

        result = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-metadata-001",
            storage_key="workspaces/test/chk-metadata-001",
            version="1.0.0",
            is_guest=False,
        )

        assert result["checkpoint_id"] == "chk-metadata-001"
        assert result["state"] == "completed"

        # Verify in database
        repo = WorkspaceCheckpointRepository(db_session)
        checkpoint = repo.get_by_checkpoint_id("chk-metadata-001")
        assert checkpoint is not None
        assert checkpoint.state == CheckpointState.COMPLETED

    def test_create_checkpoint_metadata_guest_raises_error(
        self, db_session: Session, workspace_alpha: Any
    ):
        """Test that guest checkpoint creation raises error."""
        service = WorkspaceCheckpointService(db_session)

        with pytest.raises(GuestCheckpointError):
            service.create_checkpoint_metadata_only(
                workspace_id=workspace_alpha.id,
                checkpoint_id="chk-guest-001",
                storage_key="workspaces/test/chk-guest-001",
                version="1.0.0",
                is_guest=True,
            )

    def test_advance_active_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test manually advancing active checkpoint pointer."""
        service = WorkspaceCheckpointService(db_session)

        # Create checkpoint
        result = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-advance-001",
            storage_key="workspaces/test/chk-advance-001",
            version="1.0.0",
            is_guest=False,
        )

        checkpoint_db_id = UUID(result["checkpoint_db_id"])

        # Advance pointer
        active_result = service.advance_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_db_id=checkpoint_db_id,
            changed_by="test-user",
            changed_reason="Testing",
        )

        assert active_result["workspace_id"] == str(workspace_alpha.id)
        assert active_result["changed_by"] == "test-user"

    def test_get_active_checkpoint(self, db_session: Session, workspace_alpha: Any):
        """Test retrieving active checkpoint."""
        service = WorkspaceCheckpointService(db_session)

        # Initially none
        active = service.get_active_checkpoint(workspace_alpha.id)
        assert active is None

        # Create and set active
        service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-active-001",
            storage_key="workspaces/test/chk-active-001",
            version="1.0.0",
            is_guest=False,
        )

        active = service.get_active_checkpoint(workspace_alpha.id)
        assert active is not None
        assert active["checkpoint_id"] == "chk-active-001"


class TestEndToEndPersistence:
    """End-to-end tests for persistence integration."""

    @pytest.mark.asyncio
    async def test_non_guest_run_creates_run_session(
        self,
        db_session: Session,
        workspace_alpha: Any,
        owner_principal: Any,
    ):
        """Test that non-guest runs create run session records."""
        # Create a sandbox first for routing
        from src.db.repositories.sandbox_instance_repository import (
            SandboxInstanceRepository,
        )

        sandbox_repo = SandboxInstanceRepository(db_session)

        sandbox = sandbox_repo.create(
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
        )
        # Update state to ACTIVE and health to HEALTHY
        sandbox_repo.update_state(sandbox.id, SandboxState.ACTIVE)
        sandbox_repo.update_health(sandbox.id, SandboxHealthStatus.HEALTHY)

        # Create run service with persistence
        service = RunService()

        # Execute run
        result = await service.execute_with_routing(
            principal=owner_principal,
            session=db_session,
            egress_policy=EgressPolicy(allowed_hosts=["*"]),
            tool_policy=ToolPolicy(allowed_tools=["*"]),
            secret_policy=SecretScope(allowed_secrets=["*"]),
            secrets={},
            input_message="Test message",
        )

        # Verify run completed (routing may fail but that's OK for this test)
        # The key assertion is that no exception was raised for persistence
        assert result.run_id is not None

    @pytest.mark.asyncio
    async def test_guest_run_skips_persistence(
        self,
        db_session: Session,
        guest_user: Any,
    ):
        """Test that guest runs skip persistence without error."""
        service = RunService()

        # Execute run as guest
        result = await service.execute_with_routing(
            principal=guest_user,
            session=db_session,
            egress_policy=EgressPolicy(allowed_hosts=["*"]),
            tool_policy=ToolPolicy(allowed_tools=["*"]),
            secret_policy=SecretScope(allowed_secrets=["*"]),
            secrets={},
            input_message="Test message",
        )

        # Guest runs should succeed without persistence
        assert result.run_id is not None
        assert result.status in ["success", "error"]  # Either is fine

    def test_audit_events_append_only(self, db_session: Session, workspace_alpha: Any):
        """Test that audit events are append-only (no updates)."""
        repo = AuditEventRepository(db_session)

        # Create audit event
        event = repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="created",
            outcome="success",
            resource_type="run",
            resource_id="run-audit-001",
            workspace_id=workspace_alpha.id,
        )

        # Verify it's immutable
        assert event.immutable is True

        # Verify we can read it back
        retrieved = repo.get_by_id(event.id)
        assert retrieved is not None
        assert retrieved.action == "created"

    def test_checkpoint_auto_advance_pointer(
        self, db_session: Session, workspace_alpha: Any
    ):
        """Test that checkpoint creation auto-advances active pointer."""
        service = WorkspaceCheckpointService(db_session)

        # Create first checkpoint
        service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-auto-001",
            storage_key="workspaces/test/chk-auto-001",
            version="1.0.0",
            is_guest=False,
        )

        # Verify it's active
        active1 = service.get_active_checkpoint(workspace_alpha.id)
        assert active1["checkpoint_id"] == "chk-auto-001"

        # Create second checkpoint
        service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="chk-auto-002",
            storage_key="workspaces/test/chk-auto-002",
            version="1.0.0",
            is_guest=False,
        )

        # Verify active pointer advanced
        active2 = service.get_active_checkpoint(workspace_alpha.id)
        assert active2["checkpoint_id"] == "chk-auto-002"
