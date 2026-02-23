"""API key user binding migration

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-23

This migration adds user_id binding to api_keys table and backfills
existing keys by binding them to their workspace owner.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_id to api_keys and backfill existing records."""

    # Add user_id column as nullable first (for backfill)
    op.add_column(
        "api_keys", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_api_keys_user_id", "api_keys", "users", ["user_id"], ["id"]
    )

    # Backfill: Bind existing API keys to their workspace owner
    # This is deterministic - all existing keys belong to the workspace owner
    op.execute("""
        UPDATE api_keys
        SET user_id = workspaces.owner_id
        FROM workspaces
        WHERE api_keys.workspace_id = workspaces.id
        AND api_keys.user_id IS NULL
    """)

    # Make user_id non-nullable after backfill
    op.alter_column("api_keys", "user_id", nullable=False)


def downgrade() -> None:
    """Remove user_id from api_keys."""

    # Drop foreign key constraint
    op.drop_constraint("fk_api_keys_user_id", "api_keys", type_="foreignkey")

    # Drop user_id column
    op.drop_column("api_keys", "user_id")
