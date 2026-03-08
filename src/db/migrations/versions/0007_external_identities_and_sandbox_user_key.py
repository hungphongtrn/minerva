"""Add external_identities table and sandbox external_user_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-02

Creates external_identities table for OSS end-user identity resolution
and adds external_user_id column to sandbox_instances for per-user routing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create external_identities table and add external_user_id column."""

    bind = op.get_bind()

    # Create external_identities table
    op.create_table(
        "external_identities",
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("external_user_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("workspace_id", "external_user_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "external_user_id",
            name="uq_external_identity_workspace_user",
        ),
    )

    # Add external_user_id column to sandbox_instances if not exists
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sandbox_instances")}

    if "external_user_id" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("external_user_id", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    """Drop external_identities table and remove external_user_id column."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sandbox_instances")}

    # Remove external_user_id column from sandbox_instances
    if "external_user_id" in existing_columns:
        op.drop_column("sandbox_instances", "external_user_id")

    # Drop external_identities table
    op.drop_table("external_identities")
