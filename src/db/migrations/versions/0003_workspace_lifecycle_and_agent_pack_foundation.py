"""Workspace lifecycle and agent pack foundation migration

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-24

This migration adds Phase 2 tables for workspace lifecycle, sandbox instances,
and path-linked agent pack registration with routing/locking indexes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 2 lifecycle tables with indexes and constraints."""

    # Create workspace_leases table
    op.create_table(
        "workspace_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("holder_run_id", sa.String(length=255), nullable=True),
        sa.Column("holder_identity", sa.String(length=255), nullable=True),
        sa.Column(
            "acquired_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
            name="fk_workspace_leases_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create sandbox_instances table
    op.create_table(
        "sandbox_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "profile",
            sa.Enum("local_compose", "daytona", name="sandbox_profile"),
            nullable=False,
        ),
        sa.Column("provider_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "creating",
                "active",
                "unhealthy",
                "stopping",
                "stopped",
                "failed",
                name="sandbox_state",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "health_status",
            sa.Enum(
                "healthy",
                "unhealthy",
                "unknown",
                name="sandbox_health_status",
            ),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_health_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column(
            "idle_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default="3600",
        ),
        sa.Column("agent_pack_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
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
            name="fk_sandbox_instances_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create agent_packs table
    op.create_table(
        "agent_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "validation_status",
            sa.Enum(
                "pending",
                "valid",
                "invalid",
                "stale",
                name="agent_pack_validation_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("validation_report_json", sa.Text(), nullable=True),
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
            name="fk_agent_packs_workspace_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create agent_pack_revisions table
    op.create_table(
        "agent_pack_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "agent_pack_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("change_summary_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_pack_id"],
            ["agent_packs.id"],
            name="fk_agent_pack_revisions_agent_pack_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add foreign key from sandbox_instances to agent_packs (after agent_packs created)
    op.create_foreign_key(
        "fk_sandbox_instances_agent_pack_id",
        "sandbox_instances",
        "agent_packs",
        ["agent_pack_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create indexes for routing and locking performance
    # Workspace lease indexes for lock acquisition queries
    op.create_index(
        "ix_workspace_leases_workspace_id",
        "workspace_leases",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_leases_expires_at",
        "workspace_leases",
        ["expires_at"],
    )
    op.create_index(
        "ix_workspace_leases_released_at",
        "workspace_leases",
        ["released_at"],
    )

    # Sandbox routing indexes
    op.create_index(
        "ix_sandbox_instances_workspace_id",
        "sandbox_instances",
        ["workspace_id"],
    )
    op.create_index(
        "ix_sandbox_instances_workspace_state_health",
        "sandbox_instances",
        ["workspace_id", "state", "health_status"],
    )
    op.create_index(
        "ix_sandbox_instances_profile",
        "sandbox_instances",
        ["profile"],
    )
    op.create_index(
        "ix_sandbox_instances_last_activity_at",
        "sandbox_instances",
        ["last_activity_at"],
    )

    # Agent pack indexes
    op.create_index("ix_agent_packs_workspace_id", "agent_packs", ["workspace_id"])
    op.create_index(
        "ix_agent_packs_workspace_source_path",
        "agent_packs",
        ["workspace_id", "source_path"],
    )
    op.create_index(
        "ix_agent_packs_validation_status",
        "agent_packs",
        ["validation_status"],
    )

    # Agent pack revision indexes
    op.create_index(
        "ix_agent_pack_revisions_agent_pack_id",
        "agent_pack_revisions",
        ["agent_pack_id"],
    )
    op.create_index(
        "ix_agent_pack_revisions_detected_at",
        "agent_pack_revisions",
        ["detected_at"],
    )

    # Create unique constraint to prevent duplicate active lease per workspace
    # This is a partial unique index for active leases only
    op.execute("""
        CREATE UNIQUE INDEX ix_workspace_leases_active_unique
        ON workspace_leases (workspace_id)
        WHERE released_at IS NULL
    """)

    # Create unique constraint to prevent duplicate path-linked pack per workspace
    op.create_unique_constraint(
        "uq_agent_packs_workspace_source_path",
        "agent_packs",
        ["workspace_id", "source_path"],
    )


def downgrade() -> None:
    """Drop Phase 2 lifecycle tables and indexes in reverse order."""

    # Drop indexes and constraints first
    op.drop_index("ix_workspace_leases_active_unique", table_name="workspace_leases")
    op.drop_constraint(
        "uq_agent_packs_workspace_source_path",
        "agent_packs",
        type_="unique",
    )
    op.drop_index(
        "ix_agent_pack_revisions_detected_at",
        table_name="agent_pack_revisions",
    )
    op.drop_index(
        "ix_agent_pack_revisions_agent_pack_id",
        table_name="agent_pack_revisions",
    )
    op.drop_index("ix_agent_packs_validation_status", table_name="agent_packs")
    op.drop_index("ix_agent_packs_workspace_source_path", table_name="agent_packs")
    op.drop_index("ix_agent_packs_workspace_id", table_name="agent_packs")
    op.drop_index(
        "ix_sandbox_instances_last_activity_at",
        table_name="sandbox_instances",
    )
    op.drop_index("ix_sandbox_instances_profile", table_name="sandbox_instances")
    op.drop_index(
        "ix_sandbox_instances_workspace_state_health",
        table_name="sandbox_instances",
    )
    op.drop_index(
        "ix_sandbox_instances_workspace_id",
        table_name="sandbox_instances",
    )
    op.drop_index("ix_workspace_leases_released_at", table_name="workspace_leases")
    op.drop_index("ix_workspace_leases_expires_at", table_name="workspace_leases")
    op.drop_index("ix_workspace_leases_workspace_id", table_name="workspace_leases")

    # Drop foreign keys
    op.drop_constraint(
        "fk_sandbox_instances_agent_pack_id",
        "sandbox_instances",
        type_="foreignkey",
    )

    # Drop tables in reverse dependency order
    op.drop_table("agent_pack_revisions")
    op.drop_table("agent_packs")
    op.drop_table("sandbox_instances")
    op.drop_table("workspace_leases")

    # Drop enum types (PostgreSQL-specific)
    op.execute("DROP TYPE IF EXISTS agent_pack_validation_status")
    op.execute("DROP TYPE IF EXISTS sandbox_health_status")
    op.execute("DROP TYPE IF EXISTS sandbox_state")
    op.execute("DROP TYPE IF EXISTS sandbox_profile")
