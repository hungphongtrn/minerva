"""Integration tests for Phase 3 persistence API endpoints.

Tests run timeline queries, checkpoint metadata retrieval, active pointer
management, and audit timeline visibility through the API layer.
"""

import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    RunSession,
    RunSessionState,
    RuntimeEvent,
    RuntimeEventType,
    WorkspaceCheckpoint,
    CheckpointState,
    WorkspaceActiveCheckpoint,
    AuditEvent,
    AuditEventCategory,
)
from src.db.repositories import (
    RunSessionRepository,
    RuntimeEventRepository,
    WorkspaceCheckpointRepository,
    AuditEventRepository,
)
from src.services.workspace_checkpoint_service import WorkspaceCheckpointService


class TestRunTimelineEndpoints:
    """Tests for run timeline API endpoints."""

    def test_get_run_timeline_success(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving run timeline via API."""
        # Create run session and events
        run_repo = RunSessionRepository(db_session)
        event_repo = RuntimeEventRepository(db_session)

        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="api-timeline-run-001",
            principal_id=str(workspace_alpha.owner_id),
            principal_type="user",
        )
        run_repo.mark_running(run_session.id)

        # Add events
        event_repo.log_session_started(run_session.id, actor_id="test-user")
        event_repo.create(
            run_session_id=run_session.id,
            event_type=RuntimeEventType.SESSION_COMPLETED,
            payload_json=json.dumps({"output": "success"}),
        )

        db_session.commit()

        # Query via API
        response = client.get(
            f"/api/v1/persistence/runs/api-timeline-run-001/timeline",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "api-timeline-run-001"
        assert data["session"]["run_id"] == "api-timeline-run-001"
        assert data["session"]["state"] in ["RUNNING", "running"]
        assert data["event_count"] == 2
        assert len(data["events"]) == 2

    def test_get_run_timeline_not_found(self, client: TestClient, owner_headers: dict):
        """Test retrieving timeline for non-existent run."""
        response = client.get(
            "/api/v1/persistence/runs/nonexistent-run/timeline",
            headers=owner_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_type"] == "run_not_found"

    def test_get_run_events_success(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving run events via API."""
        run_repo = RunSessionRepository(db_session)
        event_repo = RuntimeEventRepository(db_session)

        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="api-events-run-001",
        )

        # Add multiple events
        event_repo.log_session_started(run_session.id)
        event_repo.log_checkpoint_created(run_session.id, uuid4())
        event_repo.log_session_completed(run_session.id)

        db_session.commit()

        response = client.get(
            "/api/v1/persistence/runs/api-events-run-001/events",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Events should be in chronological order
        assert data[0]["event_type"] in ["SESSION_STARTED", "session_started"]

    def test_get_run_events_with_limit(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving run events with limit."""
        run_repo = RunSessionRepository(db_session)
        event_repo = RuntimeEventRepository(db_session)

        run_session = run_repo.create(
            workspace_id=workspace_alpha.id,
            run_id="api-events-run-002",
        )

        # Add 5 events
        for i in range(5):
            event_repo.create(
                run_session_id=run_session.id,
                event_type=RuntimeEventType.SESSION_STARTED,
            )

        db_session.commit()

        response = client.get(
            "/api/v1/persistence/runs/api-events-run-002/events?limit=3",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestCheckpointEndpoints:
    """Tests for checkpoint API endpoints."""

    def test_list_checkpoints_success(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test listing checkpoints via API."""
        repo = WorkspaceCheckpointRepository(db_session)

        # Create checkpoints
        for i in range(3):
            checkpoint = repo.create(
                workspace_id=workspace_alpha.id,
                checkpoint_id=f"api-chk-{i:03d}",
                version="1.0.0",
                storage_key=f"workspaces/test/chk-{i:03d}",
            )
            repo.mark_completed(checkpoint.id, storage_size_bytes=1024 * (i + 1))

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/checkpoints",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_alpha.id)
        assert data["count"] == 3
        assert len(data["checkpoints"]) == 3

    def test_list_checkpoints_with_state_filter(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test listing checkpoints with state filter."""
        repo = WorkspaceCheckpointRepository(db_session)

        # Create pending checkpoint
        repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-chk-pending",
            version="1.0.0",
            storage_key="workspaces/test/pending",
        )

        # Create completed checkpoint
        completed = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-chk-completed",
            version="1.0.0",
            storage_key="workspaces/test/completed",
        )
        repo.mark_completed(completed.id)

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/checkpoints?state=completed",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["checkpoints"][0]["checkpoint_id"] == "api-chk-completed"

    def test_get_checkpoint_details(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving checkpoint details via API."""
        repo = WorkspaceCheckpointRepository(db_session)

        checkpoint = repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-chk-detail",
            version="1.0.0",
            storage_key="workspaces/test/detail",
            manifest_json=json.dumps(
                {
                    "format_version": "1.0.0",
                    "checkpoint_id": "api-chk-detail",
                    "workspace_id": str(workspace_alpha.id),
                    "agent_pack_id": "pack-001",
                    "created_at": datetime.utcnow().isoformat(),
                    "files": [{"path": "test.txt", "size": 100, "hash": "abc123"}],
                }
            ),
        )
        repo.mark_completed(checkpoint.id, storage_size_bytes=2048)

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/checkpoints/api-chk-detail",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["checkpoint_id"] == "api-chk-detail"
        assert data["version"] == "1.0.0"
        assert data["storage_size_bytes"] == 2048
        assert data["manifest"] is not None
        assert data["manifest"]["file_count"] == 1

    def test_get_checkpoint_not_found(
        self, client: TestClient, workspace_alpha: Any, owner_headers: dict
    ):
        """Test retrieving non-existent checkpoint."""
        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/checkpoints/nonexistent",
            headers=owner_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_type"] == "checkpoint_not_found"


class TestActivePointerEndpoints:
    """Tests for active checkpoint pointer API endpoints."""

    def test_get_active_checkpoint_when_set(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving active checkpoint when one is set."""
        service = WorkspaceCheckpointService(db_session)

        # Create checkpoint
        result = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-active-chk",
            storage_key="workspaces/test/active",
            version="1.0.0",
            is_guest=False,
        )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_alpha.id)
        assert data["active_checkpoint_id"] == "api-active-chk"
        assert data["checkpoint"] is not None
        assert data["checkpoint"]["checkpoint_id"] == "api-active-chk"

    def test_get_active_checkpoint_when_not_set(
        self, client: TestClient, workspace_alpha: Any, owner_headers: dict
    ):
        """Test retrieving active checkpoint when none is set."""
        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_alpha.id)
        assert data["active_checkpoint_id"] is None
        assert data["checkpoint"] is None

    def test_get_active_checkpoint_without_details(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving active checkpoint pointer without full details."""
        service = WorkspaceCheckpointService(db_session)

        service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-active-no-detail",
            storage_key="workspaces/test/active",
            version="1.0.0",
            is_guest=False,
        )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint?include_checkpoint=false",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active_checkpoint_id"] == "api-active-no-detail"
        assert data["checkpoint"] is None


class TestAuditTimelineEndpoints:
    """Tests for audit timeline API endpoints."""

    def test_get_workspace_audit_timeline(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving workspace audit timeline."""
        repo = AuditEventRepository(db_session)

        # Create audit events
        for i in range(5):
            repo.create(
                category=AuditEventCategory.RUN_EXECUTION,
                action=f"action-{i}",
                outcome="success",
                resource_type="run",
                resource_id=f"run-{i}",
                workspace_id=workspace_alpha.id,
                actor_id="test-user",
            )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/audit",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_alpha.id)
        assert data["count"] == 5
        assert len(data["events"]) == 5
        # Events should be in reverse chronological order
        assert data["events"][0]["action"] == "action-4"

    def test_get_workspace_audit_with_category_filter(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving audit timeline with category filter."""
        repo = AuditEventRepository(db_session)

        repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="run-action",
            outcome="success",
            resource_type="run",
            resource_id="run-001",
            workspace_id=workspace_alpha.id,
        )
        repo.create(
            category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
            action="chk-action",
            outcome="success",
            resource_type="checkpoint",
            resource_id="chk-001",
            workspace_id=workspace_alpha.id,
        )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/audit?category=checkpoint_management",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["category_filter"] == "checkpoint_management"
        assert data["events"][0]["category"] in [
            "CHECKPOINT_MANAGEMENT",
            "checkpoint_management",
        ]

    def test_get_audit_event_by_id(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test retrieving specific audit event by ID."""
        repo = AuditEventRepository(db_session)

        event = repo.create(
            category=AuditEventCategory.RUN_EXECUTION,
            action="test-action",
            outcome="success",
            resource_type="run",
            resource_id="run-001",
            workspace_id=workspace_alpha.id,
        )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/audit/events/{event.id}",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(event.id)
        assert data["action"] == "test-action"
        assert data["immutable"] is True

    def test_get_audit_event_not_found(self, client: TestClient, owner_headers: dict):
        """Test retrieving non-existent audit event."""
        response = client.get(
            f"/api/v1/persistence/audit/events/{uuid4()}",
            headers=owner_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_type"] == "audit_event_not_found"


class TestWorkspaceRunsEndpoints:
    """Tests for workspace runs API endpoints."""

    def test_list_workspace_runs(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test listing runs for a workspace."""
        repo = RunSessionRepository(db_session)

        # Create runs
        for i in range(3):
            repo.create(
                workspace_id=workspace_alpha.id,
                run_id=f"api-ws-run-{i:03d}",
                principal_id=str(workspace_alpha.owner_id),
                principal_type="user",
            )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/runs",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_workspace_runs_with_state_filter(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test listing runs with state filter."""
        repo = RunSessionRepository(db_session)

        # Create running session
        running = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="api-ws-run-running",
        )
        repo.mark_running(running.id)

        # Create completed session
        completed = repo.create(
            workspace_id=workspace_alpha.id,
            run_id="api-ws-run-completed",
        )
        repo.mark_running(completed.id)
        repo.mark_completed(completed.id)

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/runs?state=completed",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["run_id"] == "api-ws-run-completed"


class TestPointerUpdateEndpoint:
    """Tests for checkpoint pointer update endpoint."""

    def test_update_active_checkpoint_as_operator(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test operator can update active checkpoint pointer."""
        service = WorkspaceCheckpointService(db_session)

        # Create first checkpoint
        result1 = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-ptr-chk-001",
            storage_key="workspaces/test/ptr-001",
            version="1.0.0",
            is_guest=False,
        )

        # Create second checkpoint (newer)
        result2 = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-ptr-chk-002",
            storage_key="workspaces/test/ptr-002",
            version="1.0.0",
            is_guest=False,
        )

        db_session.commit()

        # Update pointer to second checkpoint (should succeed - operator)
        response = client.post(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint",
            headers=owner_headers,
            json={
                "checkpoint_id": "api-ptr-chk-002",
                "reason": "Testing pointer update",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active_checkpoint_id"] == "api-ptr-chk-002"
        assert data["changed_reason"] == "Testing pointer update"

    def test_update_active_checkpoint_checkpoint_not_found(
        self, client: TestClient, workspace_alpha: Any, owner_headers: dict
    ):
        """Test updating pointer to non-existent checkpoint."""
        response = client.post(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint",
            headers=owner_headers,
            json={"checkpoint_id": "nonexistent-chk"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_type"] == "checkpoint_not_found"

    def test_get_active_checkpoint_includes_pointer_metadata(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Any,
        owner_headers: dict,
    ):
        """Test that active checkpoint response includes pointer metadata."""
        service = WorkspaceCheckpointService(db_session)

        result = service.create_checkpoint_metadata_only(
            workspace_id=workspace_alpha.id,
            checkpoint_id="api-ptr-meta-chk",
            storage_key="workspaces/test/meta",
            version="1.0.0",
            is_guest=False,
        )

        # Manually update with specific metadata
        checkpoint = (
            db_session.query(WorkspaceCheckpoint)
            .filter_by(checkpoint_id="api-ptr-meta-chk")
            .first()
        )

        service.advance_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_db_id=checkpoint.id,
            changed_by="test-operator",
            changed_reason="Initial setup",
        )

        db_session.commit()

        response = client.get(
            f"/api/v1/persistence/workspaces/{workspace_alpha.id}/active-checkpoint",
            headers=owner_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["changed_by"] == "test-operator"
        assert data["changed_reason"] == "Initial setup"
