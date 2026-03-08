"""Add sandbox bridge auth and readiness columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-26

Adds bridge token rotation fields and readiness/hydration status fields
to sandbox_instances for Phase 3.1 gateway execution production readiness.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add bridge auth and readiness/hydration columns to sandbox_instances."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sandbox_instances")}

    # Create enum type first for PostgreSQL
    if bind.dialect.name == "postgresql":
        hydration_status_enum = sa.Enum(
            "pending",
            "in_progress",
            "completed",
            "degraded",
            "failed",
            name="sandbox_hydration_status",
        )
        hydration_status_enum.create(bind, checkfirst=True)

    # Bridge auth token rotation fields
    if "bridge_auth_token" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("bridge_auth_token", sa.String(length=255), nullable=True),
        )

    if "bridge_auth_token_prev" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("bridge_auth_token_prev", sa.String(length=255), nullable=True),
        )

    if "bridge_auth_token_prev_expires_at" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("bridge_auth_token_prev_expires_at", sa.DateTime(), nullable=True),
        )

    # Readiness and hydration tracking fields
    if "identity_ready" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("identity_ready", sa.Boolean(), nullable=False, server_default="false"),
        )

    if "hydration_status" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column(
                "hydration_status",
                sa.Enum(
                    "pending",
                    "in_progress",
                    "completed",
                    "degraded",
                    "failed",
                    name="sandbox_hydration_status",
                ),
                nullable=False,
                server_default="pending",
            ),
        )

    if "hydration_retry_count" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column(
                "hydration_retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if "hydration_last_error" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("hydration_last_error", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    """Remove bridge auth and readiness/hydration columns."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sandbox_instances")}

    # Remove columns in reverse order
    columns_to_remove = [
        "hydration_last_error",
        "hydration_retry_count",
        "hydration_status",
        "identity_ready",
        "bridge_auth_token_prev_expires_at",
        "bridge_auth_token_prev",
        "bridge_auth_token",
    ]

    for column in columns_to_remove:
        if column in existing_columns:
            op.drop_column("sandbox_instances", column)

    # Drop the enum type on PostgreSQL
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS sandbox_hydration_status")
