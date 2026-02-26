"""Add gateway_url column to sandbox_instances

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-26

Fixes schema drift where ORM expects sandbox_instances.gateway_url
but database schema is missing the column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable gateway_url column to sandbox_instances."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("sandbox_instances")
    }

    if "gateway_url" not in existing_columns:
        op.add_column(
            "sandbox_instances",
            sa.Column("gateway_url", sa.String(length=512), nullable=True),
        )


def downgrade() -> None:
    """Remove gateway_url column from sandbox_instances."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("sandbox_instances")
    }

    if "gateway_url" in existing_columns:
        op.drop_column("sandbox_instances", "gateway_url")
