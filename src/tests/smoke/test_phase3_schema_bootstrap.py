"""Smoke tests for Phase 3 schema foundation.

Validates that Phase 3 models and migrations are properly configured
and the database schema includes all expected tables, relationships,
and immutable audit enforcement.
"""

import subprocess

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from src.db.models import (
    RunSession,
    RuntimeEvent,
    WorkspaceCheckpoint,
    WorkspaceActiveCheckpoint,
    AuditEvent,
)
from src.db.session import get_engine


class TestPhase3SchemaBootstrap:
    """Validate Phase 3 schema foundation is in place."""

    def _is_postgresql(self, db_session: Session) -> bool:
        """Check if the database is PostgreSQL."""
        dialect = db_session.bind.dialect.name if db_session.bind else "unknown"
        return dialect == "postgresql"

    def test_migration_chain_includes_revision_0004(self):
        """Verify migration chain includes Phase 3 persistence revision."""
        result = subprocess.run(
            ["uv", "run", "alembic", "current"],
            capture_output=True,
            text=True,
        )

        assert "0004" in result.stdout, (
            f"Expected revision 0004 in current migration. "
            f"stdout: {result.stdout}, stderr: {result.stderr}"
        )

    def test_all_phase3_tables_exist(self, db_session: Session):
        """Verify all Phase 3 tables were created by migration."""
        engine = get_engine()
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        expected_tables = [
            "run_sessions",
            "runtime_events",
            "workspace_checkpoints",
            "workspace_active_checkpoints",
            "audit_events",
        ]

        for table in expected_tables:
            assert table in table_names, (
                f"Expected table '{table}' not found in database"
            )

    def test_run_sessions_table_structure(self, db_session: Session):
        """Verify run_sessions table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("run_sessions")}

        expected_columns = [
            "id",
            "workspace_id",
            "run_id",
            "parent_run_id",
            "state",
            "principal_id",
            "principal_type",
            "sandbox_id",
            "checkpoint_id",
            "request_payload_json",
            "result_payload_json",
            "error_message",
            "error_code",
            "started_at",
            "completed_at",
            "duration_ms",
            "created_at",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in run_sessions"
            )

        # Verify foreign key to workspaces
        fks = inspector.get_foreign_keys("run_sessions")
        workspace_fk = [fk for fk in fks if "workspace_id" in fk["constrained_columns"]]
        assert len(workspace_fk) > 0, (
            "Expected foreign key from run_sessions to workspaces"
        )

    def test_runtime_events_table_structure(self, db_session: Session):
        """Verify runtime_events table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("runtime_events")}

        expected_columns = [
            "id",
            "run_session_id",
            "event_type",
            "actor_id",
            "actor_type",
            "payload_json",
            "occurred_at",
            "correlation_id",
            "created_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in runtime_events"
            )

    def test_workspace_checkpoints_table_structure(self, db_session: Session):
        """Verify workspace_checkpoints table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {
            col["name"]: col for col in inspector.get_columns("workspace_checkpoints")
        }

        expected_columns = [
            "id",
            "workspace_id",
            "checkpoint_id",
            "version",
            "storage_key",
            "storage_size_bytes",
            "state",
            "manifest_json",
            "created_by_run_id",
            "previous_checkpoint_id",
            "started_at",
            "completed_at",
            "expires_at",
            "created_at",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in workspace_checkpoints"
            )

        # Verify unique constraint on checkpoint_id
        constraints = inspector.get_unique_constraints("workspace_checkpoints")
        constraint_names = {c["name"] for c in constraints}
        assert "uq_workspace_checkpoints_checkpoint_id" in constraint_names, (
            "Expected unique constraint on checkpoint_id"
        )

    def test_workspace_active_checkpoint_table_structure(self, db_session: Session):
        """Verify workspace_active_checkpoints table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {
            col["name"]: col
            for col in inspector.get_columns("workspace_active_checkpoints")
        }

        expected_columns = [
            "id",
            "workspace_id",
            "checkpoint_id",
            "changed_by",
            "changed_reason",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in workspace_active_checkpoints"
            )

        # Verify unique constraint on workspace_id
        constraints = inspector.get_unique_constraints("workspace_active_checkpoints")
        constraint_names = {c["name"] for c in constraints}
        assert "uq_workspace_active_checkpoints_workspace" in constraint_names, (
            "Expected unique constraint on workspace_id"
        )

    def test_audit_events_table_structure(self, db_session: Session):
        """Verify audit_events table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("audit_events")}

        expected_columns = [
            "id",
            "category",
            "actor_id",
            "actor_type",
            "resource_type",
            "resource_id",
            "action",
            "outcome",
            "payload_json",
            "reason",
            "workspace_id",
            "occurred_at",
            "immutable",
            "created_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in audit_events"
            )

    def test_phase3_indexes_exist(self, db_session: Session):
        """Verify Phase 3 query indexes were created."""
        engine = get_engine()
        inspector = inspect(engine)

        # Run session indexes
        run_indexes = inspector.get_indexes("run_sessions")
        run_index_names = {idx["name"] for idx in run_indexes}
        expected_run_indexes = [
            "ix_run_sessions_workspace_id",
            "ix_run_sessions_run_id",
            "ix_run_sessions_parent_run_id",
            "ix_run_sessions_state",
            "ix_run_sessions_workspace_state",
        ]
        for idx_name in expected_run_indexes:
            assert idx_name in run_index_names, (
                f"Expected index '{idx_name}' not found on run_sessions"
            )

        # Runtime event indexes
        event_indexes = inspector.get_indexes("runtime_events")
        event_index_names = {idx["name"] for idx in event_indexes}
        expected_event_indexes = [
            "ix_runtime_events_run_session_id",
            "ix_runtime_events_event_type",
            "ix_runtime_events_occurred_at",
            "ix_runtime_events_correlation_id",
        ]
        for idx_name in expected_event_indexes:
            assert idx_name in event_index_names, (
                f"Expected index '{idx_name}' not found on runtime_events"
            )

        # Checkpoint indexes
        checkpoint_indexes = inspector.get_indexes("workspace_checkpoints")
        checkpoint_index_names = {idx["name"] for idx in checkpoint_indexes}
        expected_checkpoint_indexes = [
            "ix_workspace_checkpoints_workspace_id",
            "ix_workspace_checkpoints_checkpoint_id",
            "ix_workspace_checkpoints_state",
            "ix_workspace_checkpoints_created_by_run_id",
        ]
        for idx_name in expected_checkpoint_indexes:
            assert idx_name in checkpoint_index_names, (
                f"Expected index '{idx_name}' not found on workspace_checkpoints"
            )

        # Active checkpoint indexes
        active_indexes = inspector.get_indexes("workspace_active_checkpoints")
        active_index_names = {idx["name"] for idx in active_indexes}
        assert "ix_workspace_active_checkpoints_workspace_id" in active_index_names, (
            "Expected unique index on workspace_id for workspace_active_checkpoints"
        )

        # Audit event indexes
        audit_indexes = inspector.get_indexes("audit_events")
        audit_index_names = {idx["name"] for idx in audit_indexes}
        expected_audit_indexes = [
            "ix_audit_events_category",
            "ix_audit_events_actor_id",
            "ix_audit_events_resource_id",
            "ix_audit_events_occurred_at",
            "ix_audit_events_workspace_id",
        ]
        for idx_name in expected_audit_indexes:
            assert idx_name in audit_index_names, (
                f"Expected index '{idx_name}' not found on audit_events"
            )

    def test_models_can_be_imported(self):
        """Verify all Phase 3 models can be imported."""
        assert RunSession is not None
        assert RuntimeEvent is not None
        assert WorkspaceCheckpoint is not None
        assert WorkspaceActiveCheckpoint is not None
        assert AuditEvent is not None


class TestPhase3AuditImmutability:
    """Validate audit event immutability enforcement."""

    def _is_postgresql(self, db_session: Session) -> bool:
        """Check if the database is PostgreSQL."""
        dialect = db_session.bind.dialect.name if db_session.bind else "unknown"
        return dialect == "postgresql"

    def test_audit_events_trigger_exists(self, db_session: Session):
        """Verify immutable audit trigger exists in PostgreSQL."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test")

        result = db_session.execute(
            text("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE event_object_table = 'audit_events'
            AND trigger_name = 'audit_events_immutable'
        """)
        )
        assert result.scalar() is not None, (
            "Expected audit_events_immutable trigger not found"
        )

    def test_audit_events_insert_succeeds(self, db_session: Session):
        """Verify audit events can be inserted."""
        from uuid import uuid4

        # Insert a test audit event
        audit_id = uuid4()
        db_session.execute(
            text("""
            INSERT INTO audit_events (
                id, category, resource_type, resource_id, action, outcome,
                actor_id, actor_type, payload_json, reason, occurred_at, immutable
            ) VALUES (
                :id, 'system_operation', 'workspace', 'test-workspace-123',
                'test_action', 'success', 'test-actor', 'user',
                '{"test": true}', 'Test audit event', NOW(), true
            )
        """),
            {"id": audit_id},
        )
        db_session.commit()

        # Verify the event was inserted
        result = db_session.execute(
            text("SELECT COUNT(*) FROM audit_events WHERE id = :id"),
            {"id": audit_id},
        )
        assert result.scalar() == 1, "Audit event should be insertable"

    def test_audit_events_update_blocked(self, db_session: Session):
        """Verify audit events cannot be updated (PostgreSQL only)."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test - SQLite doesn't support triggers")

        from uuid import uuid4

        # Insert a test audit event
        audit_id = uuid4()
        db_session.execute(
            text("""
            INSERT INTO audit_events (
                id, category, resource_type, resource_id, action, outcome,
                actor_id, actor_type, occurred_at, immutable
            ) VALUES (
                :id, 'system_operation', 'workspace', 'test-workspace-456',
                'test_action', 'success', 'test-actor', 'user', NOW(), true
            )
        """),
            {"id": audit_id},
        )
        db_session.commit()

        # Attempt to update should fail
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text("UPDATE audit_events SET outcome = 'failure' WHERE id = :id"),
                {"id": audit_id},
            )
            db_session.commit()

        # The error should mention immutability
        error_msg = str(exc_info.value).lower()
        assert "immutable" in error_msg or "not allowed" in error_msg, (
            f"Expected immutability error, got: {error_msg}"
        )

    def test_audit_events_delete_blocked(self, db_session: Session):
        """Verify audit events cannot be deleted (PostgreSQL only)."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test - SQLite doesn't support triggers")

        from uuid import uuid4

        # Insert a test audit event
        audit_id = uuid4()
        db_session.execute(
            text("""
            INSERT INTO audit_events (
                id, category, resource_type, resource_id, action, outcome,
                actor_id, actor_type, occurred_at, immutable
            ) VALUES (
                :id, 'system_operation', 'workspace', 'test-workspace-789',
                'test_action', 'success', 'test-actor', 'user', NOW(), true
            )
        """),
            {"id": audit_id},
        )
        db_session.commit()

        # Attempt to delete should fail
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text("DELETE FROM audit_events WHERE id = :id"),
                {"id": audit_id},
            )
            db_session.commit()

        # The error should mention immutability
        error_msg = str(exc_info.value).lower()
        assert "immutable" in error_msg or "not allowed" in error_msg, (
            f"Expected immutability error, got: {error_msg}"
        )


class TestPhase3ActiveCheckpointPointer:
    """Validate active checkpoint pointer relationship."""

    def test_active_checkpoint_foreign_key(self, db_session: Session):
        """Verify active checkpoint points to valid checkpoint record."""
        engine = get_engine()
        inspector = inspect(engine)

        # Get foreign keys on workspace_active_checkpoints
        fks = inspector.get_foreign_keys("workspace_active_checkpoints")

        # Find the FK to workspace_checkpoints
        checkpoint_fk = [
            fk for fk in fks if fk.get("referred_table") == "workspace_checkpoints"
        ]
        assert len(checkpoint_fk) > 0, (
            "Expected foreign key from workspace_active_checkpoints to workspace_checkpoints"
        )

    def test_active_checkpoint_workspace_uniqueness(self, db_session: Session):
        """Verify only one active checkpoint per workspace."""
        engine = get_engine()
        inspector = inspect(engine)

        # Check for unique constraint/index on workspace_id
        constraints = inspector.get_unique_constraints("workspace_active_checkpoints")
        constraint_names = {c["name"] for c in constraints}

        indexes = inspector.get_indexes("workspace_active_checkpoints")
        index_columns = {
            idx["name"]: idx["column_names"] for idx in indexes if idx.get("unique")
        }

        # Should have unique constraint or unique index on workspace_id
        has_unique_constraint = (
            "uq_workspace_active_checkpoints_workspace" in constraint_names
        )
        has_unique_index = (
            "ix_workspace_active_checkpoints_workspace_id" in index_columns
        )

        assert has_unique_constraint or has_unique_index, (
            "Expected unique constraint or index on workspace_id for singleton pattern"
        )
