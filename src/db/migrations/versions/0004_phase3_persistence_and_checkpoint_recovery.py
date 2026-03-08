"""Phase 3 persistence and checkpoint recovery migration

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-26

This migration adds Phase 3 tables for runtime persistence, checkpoint metadata,
and immutable audit logging with database-level append-only enforcement.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 3 persistence tables with indexes and immutable audit enforcement."""

    # Create run_sessions table
    op.create_table(
        "run_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("parent_run_id", sa.String(length=255), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "queued",
                "running",
                "paused",
                "completed",
                "failed",
                "cancelled",
                name="run_session_state",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("principal_id", sa.String(length=255), nullable=True),
        sa.Column("principal_type", sa.String(length=50), nullable=True),
        sa.Column("sandbox_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checkpoint_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_payload_json", sa.Text(), nullable=True),
        sa.Column("result_payload_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_run_sessions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_run_sessions_run_id"),
    )

    # Create runtime_events table
    op.create_table(
        "runtime_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "session_started",
                "session_paused",
                "session_resumed",
                "session_completed",
                "session_failed",
                "session_cancelled",
                "checkpoint_created",
                "checkpoint_restore_started",
                "checkpoint_restore_completed",
                "checkpoint_restore_failed",
                "checkpoint_fallback_used",
                "policy_violation",
                "rate_limit_exceeded",
                name="runtime_event_type",
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["run_session_id"],
            ["run_sessions.id"],
            name="fk_runtime_events_run_session_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create workspace_checkpoints table
    op.create_table(
        "workspace_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("storage_size_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "in_progress",
                "completed",
                "failed",
                "partial",
                name="checkpoint_state",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("manifest_json", sa.Text(), nullable=True),
        sa.Column("created_by_run_id", sa.String(length=255), nullable=True),
        sa.Column("previous_checkpoint_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_checkpoints_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_checkpoint_id"],
            ["workspace_checkpoints.id"],
            name="fk_workspace_checkpoints_previous",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_id", name="uq_workspace_checkpoints_checkpoint_id"),
    )

    # Create workspace_active_checkpoints table
    op.create_table(
        "workspace_active_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_by", sa.String(length=255), nullable=True),
        sa.Column("changed_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_active_checkpoints_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["workspace_checkpoints.id"],
            name="fk_workspace_active_checkpoints_checkpoint_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_active_checkpoints_workspace"),
    )

    # Create audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "run_execution",
                "checkpoint_management",
                "policy_enforcement",
                "system_operation",
                name="audit_event_category",
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "immutable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_audit_events_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add foreign keys to run_sessions (after checkpoint table is created)
    op.create_foreign_key(
        "fk_run_sessions_sandbox_id",
        "run_sessions",
        "sandbox_instances",
        ["sandbox_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_run_sessions_checkpoint_id",
        "run_sessions",
        "workspace_checkpoints",
        ["checkpoint_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create indexes for query patterns
    # Run session indexes
    op.create_index(
        "ix_run_sessions_workspace_id",
        "run_sessions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_run_sessions_run_id",
        "run_sessions",
        ["run_id"],
    )
    op.create_index(
        "ix_run_sessions_parent_run_id",
        "run_sessions",
        ["parent_run_id"],
    )
    op.create_index(
        "ix_run_sessions_state",
        "run_sessions",
        ["state"],
    )
    op.create_index(
        "ix_run_sessions_workspace_state",
        "run_sessions",
        ["workspace_id", "state"],
    )

    # Runtime event indexes
    op.create_index(
        "ix_runtime_events_run_session_id",
        "runtime_events",
        ["run_session_id"],
    )
    op.create_index(
        "ix_runtime_events_event_type",
        "runtime_events",
        ["event_type"],
    )
    op.create_index(
        "ix_runtime_events_occurred_at",
        "runtime_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_runtime_events_correlation_id",
        "runtime_events",
        ["correlation_id"],
    )

    # Checkpoint indexes
    op.create_index(
        "ix_workspace_checkpoints_workspace_id",
        "workspace_checkpoints",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_checkpoints_checkpoint_id",
        "workspace_checkpoints",
        ["checkpoint_id"],
    )
    op.create_index(
        "ix_workspace_checkpoints_state",
        "workspace_checkpoints",
        ["state"],
    )
    op.create_index(
        "ix_workspace_checkpoints_created_by_run_id",
        "workspace_checkpoints",
        ["created_by_run_id"],
    )

    # Active checkpoint indexes
    op.create_index(
        "ix_workspace_active_checkpoints_workspace_id",
        "workspace_active_checkpoints",
        ["workspace_id"],
        unique=True,
    )
    op.create_index(
        "ix_workspace_active_checkpoints_checkpoint_id",
        "workspace_active_checkpoints",
        ["checkpoint_id"],
    )

    # Audit event indexes
    op.create_index(
        "ix_audit_events_category",
        "audit_events",
        ["category"],
    )
    op.create_index(
        "ix_audit_events_actor_id",
        "audit_events",
        ["actor_id"],
    )
    op.create_index(
        "ix_audit_events_resource_id",
        "audit_events",
        ["resource_id"],
    )
    op.create_index(
        "ix_audit_events_occurred_at",
        "audit_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_audit_events_workspace_id",
        "audit_events",
        ["workspace_id"],
    )

    # Create immutable audit trigger for PostgreSQL
    # This prevents UPDATE and DELETE on audit_events table
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Audit events are immutable: % operations are not allowed on audit_events', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_mutation();
    """)


def downgrade() -> None:
    """Drop Phase 3 persistence tables and triggers in reverse order."""

    # Drop immutable audit trigger first
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")

    # Drop indexes
    op.drop_index("ix_audit_events_workspace_id", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_category", table_name="audit_events")

    op.drop_index(
        "ix_workspace_active_checkpoints_checkpoint_id",
        table_name="workspace_active_checkpoints",
    )
    op.drop_index(
        "ix_workspace_active_checkpoints_workspace_id",
        table_name="workspace_active_checkpoints",
    )

    op.drop_index(
        "ix_workspace_checkpoints_created_by_run_id",
        table_name="workspace_checkpoints",
    )
    op.drop_index("ix_workspace_checkpoints_state", table_name="workspace_checkpoints")
    op.drop_index(
        "ix_workspace_checkpoints_checkpoint_id",
        table_name="workspace_checkpoints",
    )
    op.drop_index(
        "ix_workspace_checkpoints_workspace_id",
        table_name="workspace_checkpoints",
    )

    op.drop_index("ix_runtime_events_correlation_id", table_name="runtime_events")
    op.drop_index("ix_runtime_events_occurred_at", table_name="runtime_events")
    op.drop_index("ix_runtime_events_event_type", table_name="runtime_events")
    op.drop_index("ix_runtime_events_run_session_id", table_name="runtime_events")

    op.drop_index("ix_run_sessions_workspace_state", table_name="run_sessions")
    op.drop_index("ix_run_sessions_state", table_name="run_sessions")
    op.drop_index("ix_run_sessions_parent_run_id", table_name="run_sessions")
    op.drop_index("ix_run_sessions_run_id", table_name="run_sessions")
    op.drop_index("ix_run_sessions_workspace_id", table_name="run_sessions")

    # Drop foreign keys
    op.drop_constraint(
        "fk_run_sessions_checkpoint_id",
        "run_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_run_sessions_sandbox_id",
        "run_sessions",
        type_="foreignkey",
    )

    # Drop tables in reverse dependency order
    op.drop_table("audit_events")
    op.drop_table("workspace_active_checkpoints")
    op.drop_table("runtime_events")
    op.drop_table("workspace_checkpoints")
    op.drop_table("run_sessions")

    # Drop enum types (PostgreSQL-specific)
    op.execute("DROP TYPE IF EXISTS audit_event_category")
    op.execute("DROP TYPE IF EXISTS checkpoint_state")
    op.execute("DROP TYPE IF EXISTS runtime_event_type")
    op.execute("DROP TYPE IF EXISTS run_session_state")
