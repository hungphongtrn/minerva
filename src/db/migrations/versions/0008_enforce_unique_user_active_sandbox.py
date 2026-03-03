"""Enforce one active lifecycle sandbox per external user.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-03

Adds a partial unique index to prevent concurrent creation of multiple
active lifecycle sandboxes (pending/creating/active) for the same
workspace-scoped external user.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create partial unique index for user lifecycle sandbox rows."""
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sandbox_user_active_lifecycle
        ON sandbox_instances (workspace_id, external_user_id)
        WHERE external_user_id IS NOT NULL
          AND state IN ('pending', 'creating', 'active')
        """
    )


def downgrade() -> None:
    """Drop partial unique index for user lifecycle sandbox rows."""
    op.execute("DROP INDEX IF EXISTS uq_sandbox_user_active_lifecycle")
