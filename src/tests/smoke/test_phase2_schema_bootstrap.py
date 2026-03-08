"""Smoke tests for Phase 2 schema foundation.

Validates that Phase 2 models and migrations are properly configured
and the database schema includes all expected tables and relationships.
"""

import subprocess

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from src.db.models import (
    WorkspaceLease,
    SandboxInstance,
    AgentPack,
    AgentPackRevision,
)
from src.db.session import get_engine


class TestPhase2SchemaBootstrap:
    """Validate Phase 2 schema foundation is in place."""

    def _is_postgresql(self, db_session: Session) -> bool:
        """Check if the database is PostgreSQL."""
        dialect = db_session.bind.dialect.name if db_session.bind else "unknown"
        return dialect == "postgresql"

    def test_migration_chain_includes_revision_0003(self):
        """Verify migration chain includes Phase 2 foundation revision."""
        # Run alembic current and capture output
        result = subprocess.run(
            ["uv", "run", "alembic", "current"],
            capture_output=True,
            text=True,
        )

        # Verify 0003 is in the output
        assert "0003" in result.stdout, (
            f"Expected revision 0003 in current migration. "
            f"stdout: {result.stdout}, stderr: {result.stderr}"
        )

    def test_all_phase2_tables_exist(self, db_session: Session):
        """Verify all Phase 2 tables were created by migration."""
        engine = get_engine()
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        expected_tables = [
            "workspace_leases",
            "sandbox_instances",
            "agent_packs",
            "agent_pack_revisions",
        ]

        for table in expected_tables:
            assert table in table_names, f"Expected table '{table}' not found in database"

    def test_workspace_leases_table_structure(self, db_session: Session):
        """Verify workspace_leases table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("workspace_leases")}

        expected_columns = [
            "id",
            "workspace_id",
            "holder_run_id",
            "holder_identity",
            "acquired_at",
            "expires_at",
            "released_at",
            "version",
            "created_at",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in workspace_leases"
            )

        # Verify foreign key to workspaces
        fks = inspector.get_foreign_keys("workspace_leases")
        workspace_fk = [fk for fk in fks if "workspace_id" in fk["constrained_columns"]]
        assert len(workspace_fk) > 0, "Expected foreign key from workspace_leases to workspaces"

    def test_sandbox_instances_table_structure(self, db_session: Session):
        """Verify sandbox_instances table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("sandbox_instances")}

        expected_columns = [
            "id",
            "workspace_id",
            "profile",
            "provider_ref",
            "state",
            "health_status",
            "last_health_at",
            "last_activity_at",
            "idle_ttl_seconds",
            "agent_pack_id",
            "stopped_at",
            "created_at",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in sandbox_instances"
            )

    def test_agent_packs_table_structure(self, db_session: Session):
        """Verify agent_packs table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("agent_packs")}

        expected_columns = [
            "id",
            "workspace_id",
            "name",
            "source_path",
            "source_digest",
            "is_active",
            "last_validated_at",
            "validation_status",
            "validation_report_json",
            "created_at",
            "updated_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, f"Expected column '{col_name}' not found in agent_packs"

    def test_agent_pack_revisions_table_structure(self, db_session: Session):
        """Verify agent_pack_revisions table has expected columns."""
        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"]: col for col in inspector.get_columns("agent_pack_revisions")}

        expected_columns = [
            "id",
            "agent_pack_id",
            "source_digest",
            "detected_at",
            "change_summary_json",
            "created_at",
        ]

        for col_name in expected_columns:
            assert col_name in columns, (
                f"Expected column '{col_name}' not found in agent_pack_revisions"
            )

    def test_routing_indexes_exist(self, db_session: Session):
        """Verify routing and locking indexes were created."""
        engine = get_engine()
        inspector = inspect(engine)

        # Check sandbox routing indexes
        sandbox_indexes = inspector.get_indexes("sandbox_instances")
        index_names = {idx["name"] for idx in sandbox_indexes}

        expected_sandbox_indexes = [
            "ix_sandbox_instances_workspace_id",
            "ix_sandbox_instances_workspace_state_health",
            "ix_sandbox_instances_profile",
            "ix_sandbox_instances_last_activity_at",
        ]

        for idx_name in expected_sandbox_indexes:
            assert idx_name in index_names, (
                f"Expected index '{idx_name}' not found on sandbox_instances"
            )

        # Check agent pack uniqueness index
        pack_indexes = inspector.get_indexes("agent_packs")
        pack_index_names = {idx["name"] for idx in pack_indexes}

        assert "ix_agent_packs_workspace_source_path" in pack_index_names, (
            "Expected workspace+path index on agent_packs"
        )

    def test_lease_unique_constraint(self, db_session: Session):
        """Verify unique constraint for active lease per workspace."""
        engine = get_engine()
        inspector = inspect(engine)
        indexes = inspector.get_indexes("workspace_leases")
        index_names = {idx["name"] for idx in indexes}

        assert "ix_workspace_leases_active_unique" in index_names, (
            "Expected unique partial index for active leases"
        )

    def test_models_can_be_imported(self):
        """Verify all Phase 2 models can be imported."""
        # This test is implicit - if imports fail, the test fails
        assert WorkspaceLease is not None
        assert SandboxInstance is not None
        assert AgentPack is not None
        assert AgentPackRevision is not None

    def test_repositories_can_be_imported(self):
        """Verify repository modules can be imported."""
        from src.db.repositories import (
            WorkspaceLeaseRepository,
            SandboxInstanceRepository,
            AgentPackRepository,
        )

        assert WorkspaceLeaseRepository is not None
        assert SandboxInstanceRepository is not None
        assert AgentPackRepository is not None

    def test_sandbox_state_enum_exists(self, db_session: Session):
        """Verify sandbox state enum was created (PostgreSQL only)."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test")

        from sqlalchemy import text

        result = db_session.execute(
            text("""
            SELECT typname FROM pg_type WHERE typname = 'sandbox_state'
        """)
        )
        assert result.scalar() is not None, "Expected sandbox_state enum not found"

    def test_sandbox_profile_enum_exists(self, db_session: Session):
        """Verify sandbox profile enum was created (PostgreSQL only)."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test")

        from sqlalchemy import text

        result = db_session.execute(
            text("""
            SELECT typname FROM pg_type WHERE typname = 'sandbox_profile'
        """)
        )
        assert result.scalar() is not None, "Expected sandbox_profile enum not found"

    def test_agent_pack_validation_enum_exists(self, db_session: Session):
        """Verify agent pack validation status enum was created (PostgreSQL only)."""
        if not self._is_postgresql(db_session):
            pytest.skip("PostgreSQL-specific test")

        from sqlalchemy import text

        result = db_session.execute(
            text("""
            SELECT typname FROM pg_type WHERE typname = 'agent_pack_validation_status'
        """)
        )
        assert result.scalar() is not None, "Expected agent_pack_validation_status enum not found"
