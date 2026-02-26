"""Integration tests for checkpoint restore behavior.

Tests the cold-start restore flow with fallback policy:
- Active checkpoint restore success
- Fallback to previous checkpoint on active failure
- Single retry on transient failure
- Fresh start after repeated failure
- Queued responses during restore
"""

import json
import pytest
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from unittest.mock import Mock, patch, AsyncMock

import pytest_asyncio
from sqlalchemy.orm import Session

from src.db.models import (
    CheckpointState,
    AuditEventCategory,
    Workspace,
    User,
)
from src.db.repositories.workspace_checkpoint_repository import (
    WorkspaceCheckpointRepository,
)
from src.db.repositories.audit_event_repository import AuditEventRepository
from src.services.checkpoint_restore_service import (
    CheckpointRestoreService,
    RestoreOutcome,
    ManifestValidationError,
)
from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
from src.infrastructure.sandbox.providers.base import SandboxState


class TestCheckpointRestoreContract:
    """Tests for restore service contract and lifecycle integration."""

    def test_restore_service_initialization(self, db_session: Session):
        """Verify restore service can be initialized with dependencies."""
        service = CheckpointRestoreService(db_session)
        assert service is not None
        assert service._session == db_session

    def test_restore_outcome_enum_values(self):
        """Verify RestoreOutcome enum has expected values."""
        assert RestoreOutcome.SUCCESS is not None
        assert RestoreOutcome.FALLBACK_SUCCESS is not None
        assert RestoreOutcome.FRESH_START is not None
        assert RestoreOutcome.IN_PROGRESS is not None
        assert RestoreOutcome.FAILED is not None

    def test_manifest_validation_error(self):
        """Verify ManifestValidationError includes context."""
        err = ManifestValidationError(
            "Test error",
            workspace_id=uuid4(),
            checkpoint_id="test-checkpoint",
        )
        assert "Test error" in str(err)
        assert err.workspace_id is not None
        assert err.checkpoint_id == "test-checkpoint"


class TestCheckpointRestoreActiveSuccess:
    """Tests for successful restore from active checkpoint."""

    @pytest.mark.asyncio
    async def test_restore_from_active_checkpoint(
        self,
        db_session: Session,
        workspace_owner: User,
        workspace_alpha: Workspace,
    ):
        """Verify successful restore from active checkpoint."""
        # Create checkpoint repository
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)
        audit_repo = AuditEventRepository(db_session)

        # Create a completed checkpoint
        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-active-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-001.tar.zst",
            created_by_run_id="run-001",
            manifest_json=json.dumps(
                {
                    "checkpoint_id": "checkpoint-active-001",
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                    "session_data": {"key": "value"},
                }
            ),
        )

        # Mark as completed
        checkpoint_repo.mark_completed(checkpoint.id)

        # Set as active
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        # Commit to persist
        db_session.commit()

        # Create restore service
        restore_service = CheckpointRestoreService(db_session)

        # Perform restore
        result = await restore_service.restore_workspace(workspace_alpha.id)

        # Verify success
        assert result.outcome == RestoreOutcome.SUCCESS
        assert result.workspace_id == workspace_alpha.id
        assert result.checkpoint_id == "checkpoint-active-001"
        assert result.restored_data is not None
        assert result.restored_data.get("session") == {"key": "value"}
        assert result.fresh_start is False

        # Verify audit event created
        audit_events = audit_repo.list_by_resource(
            resource_type="checkpoint",
            resource_id="checkpoint-active-001",
        )
        assert len(audit_events) >= 1
        assert any(e.action == "restore" for e in audit_events)

    @pytest.mark.asyncio
    async def test_restore_no_active_checkpoint_returns_fresh_start(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify fresh start when no active checkpoint exists."""
        restore_service = CheckpointRestoreService(db_session)

        result = await restore_service.restore_workspace(workspace_alpha.id)

        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.fresh_start is True
        assert result.checkpoint_id is None

    @pytest.mark.asyncio
    async def test_restore_explicit_fresh_start(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify explicit fresh start skips restore."""
        restore_service = CheckpointRestoreService(db_session)

        result = await restore_service.restore_workspace(
            workspace_alpha.id,
            attempt_restore=False,
        )

        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.fresh_start is True


class TestCheckpointRestoreFallback:
    """Tests for fallback to previous checkpoint."""

    @pytest.mark.asyncio
    async def test_fallback_to_previous_checkpoint(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify fallback to previous checkpoint when active fails."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)
        audit_repo = AuditEventRepository(db_session)

        # Create first (older) checkpoint - this will be the fallback
        checkpoint_old = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-old-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-old.tar.zst",
            manifest_json=json.dumps(
                {
                    "checkpoint_id": "checkpoint-old-001",
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                    "session_data": {"fallback": True},
                }
            ),
        )
        checkpoint_repo.mark_completed(checkpoint_old.id)

        # Create second (active) checkpoint with invalid manifest
        checkpoint_new = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-new-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-new.tar.zst",
            previous_checkpoint_id=checkpoint_old.id,
            manifest_json=json.dumps(
                {
                    # Missing required fields to trigger validation failure
                    "checkpoint_id": "checkpoint-new-001",
                }
            ),
        )
        checkpoint_repo.mark_completed(checkpoint_new.id)

        # Set new checkpoint as active
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint_new.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)

        # Mock _do_restore to fail on the active checkpoint
        original_do_restore = restore_service._do_restore

        async def mock_do_restore(
            workspace_id, checkpoint, actor_id, is_fallback=False, attempt_number=1
        ):
            if checkpoint.checkpoint_id == "checkpoint-new-001" and not is_fallback:
                raise ManifestValidationError("Invalid manifest")
            return await original_do_restore(
                workspace_id, checkpoint, actor_id, is_fallback, attempt_number
            )

        restore_service._do_restore = mock_do_restore

        result = await restore_service.restore_workspace(workspace_alpha.id)

        # Should fall back to old checkpoint
        assert result.outcome == RestoreOutcome.FALLBACK_SUCCESS
        assert result.checkpoint_id == "checkpoint-new-001"
        assert result.fallback_checkpoint_id == "checkpoint-old-001"
        assert result.restored_data is not None
        assert result.restored_data.get("session", {}).get("fallback") is True

        # Verify fallback audit event
        audit_events = audit_repo.list_by_resource(
            resource_type="checkpoint",
            resource_id="checkpoint-old-001",
        )
        assert any(e.action == "restore_fallback" for e in audit_events)

    @pytest.mark.asyncio
    async def test_fresh_start_when_all_checkpoints_fail(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify fresh start when all checkpoints fail validation."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)

        # Create checkpoint with invalid manifest
        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-invalid-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-invalid.tar.zst",
            manifest_json="invalid json {{",  # Invalid JSON
        )
        checkpoint_repo.mark_completed(checkpoint.id)

        # Set as active
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)
        result = await restore_service.restore_workspace(workspace_alpha.id)

        # Should return fresh start
        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.fresh_start is True
        assert result.checkpoint_id == "checkpoint-invalid-001"


class TestCheckpointRestoreRetry:
    """Tests for retry behavior on transient failures."""

    @pytest.mark.asyncio
    async def test_single_retry_on_transient_failure(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify single retry attempt on transient failure."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)
        audit_repo = AuditEventRepository(db_session)

        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-retry-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-retry.tar.zst",
            manifest_json=json.dumps(
                {
                    "checkpoint_id": "checkpoint-retry-001",
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                }
            ),
        )
        checkpoint_repo.mark_completed(checkpoint.id)
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)

        # Track call count
        call_count = [0]

        async def mock_do_restore(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Transient error")
            return await CheckpointRestoreService._do_restore(
                restore_service, *args, **kwargs
            )

        restore_service._do_restore = mock_do_restore

        result = await restore_service.restore_workspace(workspace_alpha.id)

        # Should succeed after retry
        assert result.outcome == RestoreOutcome.SUCCESS
        assert call_count[0] == 2  # Initial + 1 retry

        # Verify retry audit event
        audit_events = audit_repo.list_by_resource(
            resource_type="checkpoint",
            resource_id="checkpoint-retry-001",
        )
        assert any(e.action == "restore_retry" for e in audit_events)

    @pytest.mark.asyncio
    async def test_no_retry_on_validation_error(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify no retry on validation errors (not retryable)."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)

        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-val-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-val.tar.zst",
            manifest_json=json.dumps(
                {
                    "checkpoint_id": "wrong-id",  # Mismatch triggers validation error
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                }
            ),
        )
        checkpoint_repo.mark_completed(checkpoint.id)
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)
        call_count = [0]

        async def mock_do_restore(*args, **kwargs):
            call_count[0] += 1
            raise ManifestValidationError("Validation failed")

        restore_service._do_restore = mock_do_restore

        result = await restore_service.restore_workspace(workspace_alpha.id)

        # Should not retry validation errors
        assert call_count[0] == 1  # Only initial attempt
        assert result.outcome == RestoreOutcome.FAILED


class TestCheckpointRestoreAudit:
    """Tests for audit event logging during restore."""

    @pytest.mark.asyncio
    async def test_restore_success_audit_event(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify audit event created on restore success."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)
        audit_repo = AuditEventRepository(db_session)

        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-audit-001",
            version="1.0.0",
            storage_key="workspaces/test/checkpoint-audit.tar.zst",
            manifest_json=json.dumps(
                {
                    "checkpoint_id": "checkpoint-audit-001",
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                }
            ),
        )
        checkpoint_repo.mark_completed(checkpoint.id)
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)
        result = await restore_service.restore_workspace(
            workspace_alpha.id,
            actor_id="test-actor",
        )

        assert result.audit_event_id is not None

        # Verify audit event details
        audit_event = audit_repo.get_by_id(result.audit_event_id)
        assert audit_event is not None
        assert audit_event.category == AuditEventCategory.CHECKPOINT_MANAGEMENT
        assert audit_event.action == "restore"
        assert audit_event.outcome == "success"
        assert audit_event.actor_id == "test-actor"
        assert audit_event.workspace_id == workspace_alpha.id

    @pytest.mark.asyncio
    async def test_fresh_start_audit_event(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify audit event created on fresh start."""
        audit_repo = AuditEventRepository(db_session)
        restore_service = CheckpointRestoreService(db_session)

        result = await restore_service.restore_workspace(
            workspace_alpha.id,
            actor_id="test-actor",
        )

        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.audit_event_id is not None

        audit_event = audit_repo.get_by_id(result.audit_event_id)
        assert audit_event is not None
        assert audit_event.action == "fresh_start_no_checkpoint"
        assert audit_event.outcome == "success"


class TestCheckpointRestoreLifecycleIntegration:
    """Tests for restore integration with workspace lifecycle."""

    def test_lifecycle_restore_tracking(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify lifecycle service tracks restore state."""
        lifecycle = WorkspaceLifecycleService(session=db_session)

        # Initially no restore in progress
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is False
        assert lifecycle.get_restore_checkpoint_id(workspace_alpha.id) is None

        # Mark restore started
        lifecycle.mark_restore_started(workspace_alpha.id, "checkpoint-001")

        # Now restore is in progress
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is True
        assert (
            lifecycle.get_restore_checkpoint_id(workspace_alpha.id) == "checkpoint-001"
        )

        # Mark restore completed
        lifecycle.mark_restore_completed(workspace_alpha.id)

        # Restore no longer in progress
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is False
        assert lifecycle.get_restore_checkpoint_id(workspace_alpha.id) is None

    def test_lifecycle_restore_timeout(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify restore tracking times out after 5 minutes."""
        lifecycle = WorkspaceLifecycleService(session=db_session)

        # Manually inject an old restore entry
        lifecycle._restore_in_progress[str(workspace_alpha.id)] = {
            "started_at": datetime.utcnow() - timedelta(minutes=6),
            "checkpoint_id": "old-checkpoint",
        }

        # Should report not in progress due to timeout
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is False

    def test_lifecycle_restore_failure_cleanup(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify restore tracking cleaned up on failure."""
        lifecycle = WorkspaceLifecycleService(session=db_session)

        # Mark restore started
        lifecycle.mark_restore_started(workspace_alpha.id, "checkpoint-001")
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is True

        # Mark restore failed
        lifecycle.mark_restore_failed(workspace_alpha.id)

        # Restore tracking cleaned up
        assert lifecycle.is_restore_in_progress(workspace_alpha.id) is False


class TestCheckpointRestoreManifestValidation:
    """Tests for manifest validation during restore."""

    def test_valid_manifest_passes_validation(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify valid manifest passes validation."""
        restore_service = CheckpointRestoreService(db_session)

        manifest = {
            "checkpoint_id": "test-checkpoint",
            "version": "1.0.0",
            "created_at": datetime.utcnow().isoformat(),
            "session_data": {"key": "value"},
        }

        # Should not raise
        restore_service._validate_manifest(manifest, "test-checkpoint")

    def test_missing_required_fields_fails(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify missing required fields fails validation."""
        restore_service = CheckpointRestoreService(db_session)

        manifest = {
            "checkpoint_id": "test-checkpoint",
            # Missing version and created_at
        }

        with pytest.raises(ManifestValidationError) as exc_info:
            restore_service._validate_manifest(manifest, "test-checkpoint")

        assert "version" in str(exc_info.value)

    def test_checkpoint_id_mismatch_fails(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify checkpoint_id mismatch fails validation."""
        restore_service = CheckpointRestoreService(db_session)

        manifest = {
            "checkpoint_id": "wrong-checkpoint",
            "version": "1.0.0",
            "created_at": datetime.utcnow().isoformat(),
        }

        with pytest.raises(ManifestValidationError) as exc_info:
            restore_service._validate_manifest(manifest, "expected-checkpoint")

        assert "mismatch" in str(exc_info.value)

    def test_invalid_json_fails(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify invalid JSON fails parsing."""
        restore_service = CheckpointRestoreService(db_session)

        with pytest.raises(ManifestValidationError) as exc_info:
            restore_service._parse_manifest("not valid json {{")

        assert "Invalid JSON" in str(exc_info.value)


class TestCheckpointRestoreArchiveValidation:
    """Tests for archive checksum validation."""

    def test_valid_checksum_passes(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify valid checksum passes validation."""
        restore_service = CheckpointRestoreService(db_session)

        data = b"test data for checksum"
        # Calculate actual checksum
        import hashlib

        expected_checksum = hashlib.sha256(data).hexdigest()

        # Should not raise
        result = restore_service.validate_archive_checksum(
            "test-checkpoint", expected_checksum, data
        )
        assert result is True

    def test_invalid_checksum_fails(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify invalid checksum fails validation."""
        restore_service = CheckpointRestoreService(db_session)

        data = b"test data for checksum"

        with pytest.raises(Exception) as exc_info:
            restore_service.validate_archive_checksum(
                "test-checkpoint", "invalid-checksum", data
            )

        assert "Checksum mismatch" in str(exc_info.value)


class TestCheckpointRestoreFreshStartContinuation:
    """Tests for degraded fresh-start continuation."""

    @pytest.mark.asyncio
    async def test_fresh_start_allows_normal_execution(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify fresh start allows normal run execution to continue."""
        restore_service = CheckpointRestoreService(db_session)

        result = await restore_service.restore_workspace(workspace_alpha.id)

        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.fresh_start is True
        assert result.restored_data is None  # No checkpoint data

        # Fresh start should not block execution
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_fresh_start_with_fallback_decision_recorded(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify fresh start decision is recorded in audit."""
        checkpoint_repo = WorkspaceCheckpointRepository(db_session)
        audit_repo = AuditEventRepository(db_session)

        # Create checkpoint that will fail validation
        checkpoint = checkpoint_repo.create(
            workspace_id=workspace_alpha.id,
            checkpoint_id="checkpoint-bad-001",
            version="1.0.0",
            storage_key="workspaces/test/bad.tar.zst",
            manifest_json="invalid json",  # Will fail validation
        )
        checkpoint_repo.mark_completed(checkpoint.id)
        checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_alpha.id,
            checkpoint_id=checkpoint.id,
        )

        db_session.commit()

        restore_service = CheckpointRestoreService(db_session)
        result = await restore_service.restore_workspace(workspace_alpha.id)

        assert result.outcome == RestoreOutcome.FRESH_START
        assert result.fresh_start is True
        assert result.audit_event_id is not None

        # Verify audit event captures the fallback decision
        audit_event = audit_repo.get_by_id(result.audit_event_id)
        assert audit_event is not None
        assert "fresh_start" in audit_event.action
        assert audit_event.payload_json is not None
        payload = json.loads(audit_event.payload_json)
        assert "active_checkpoint_id" in payload


class TestCheckpointRestoreSandboxState:
    """Tests for restore-aware sandbox state handling."""

    def test_sandbox_restoring_state(self):
        """Verify RESTORING state exists in SandboxState enum."""
        assert hasattr(SandboxState, "RESTORING")
        assert SandboxState.RESTORING is not None

    def test_restore_state_tracking(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
    ):
        """Verify restore state is tracked in lifecycle target."""
        from src.services.workspace_lifecycle_service import LifecycleTarget

        target = LifecycleTarget(
            workspace=workspace_alpha,
            lease_acquired=False,
            lease_result=None,
            sandbox=None,
            routing_result=None,
            restore_state="in_progress",
            restore_checkpoint_id="checkpoint-001",
            queued=True,
        )

        assert target.restore_state == "in_progress"
        assert target.restore_checkpoint_id == "checkpoint-001"
        assert target.queued is True
