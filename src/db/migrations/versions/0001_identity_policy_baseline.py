"""Initial schema + RLS baseline migration

Revision ID: 0001
Revises:
Create Date: 2026-02-23

This migration creates the baseline identity and policy tables
with Row Level Security (RLS) enforcement.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create baseline identity tables with RLS."""

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_guest", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    # Create workspaces table
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=False)

    # Create membership_role enum
    membership_role = postgresql.ENUM(
        "owner", "admin", "member", name="membership_role"
    )
    membership_role.create(op.get_bind(), checkfirst=True)

    # Create memberships table
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "owner",
                "admin",
                "member",
                name="membership_role",
                create_type=False,
            ),
            nullable=False,
            server_default="member",
        ),
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
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "workspace_id", name="uq_membership_user_workspace"
        ),
    )

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=False)

    # Create workspace_resources table
    op.create_table(
        "workspace_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Enable Row Level Security on tenant tables
    # Apply to workspaces (owner can access)
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")

    # Apply to memberships (members can access their own)
    op.execute("ALTER TABLE memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE memberships FORCE ROW LEVEL SECURITY")

    # Apply to api_keys (workspace scoped)
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE api_keys FORCE ROW LEVEL SECURITY")

    # Apply to workspace_resources (workspace scoped)
    op.execute("ALTER TABLE workspace_resources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_resources FORCE ROW LEVEL SECURITY")

    # Create RLS policies with real tenant predicates
    # These policies enforce workspace isolation at the database boundary

    # Workspaces: User can access if they are owner OR if workspace_id matches context
    op.execute("""
        CREATE POLICY workspace_isolation ON workspaces
        FOR ALL
        USING (
            -- Owner can access their workspaces
            owner_id::text = COALESCE(current_setting('app.user_id', true), '')
            OR
            -- Or workspace_id matches the RLS context
            id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
        WITH CHECK (
            -- Can only modify workspaces they own
            owner_id::text = COALESCE(current_setting('app.user_id', true), '')
        )
    """)

    # Memberships: User can access memberships in their workspace
    op.execute("""
        CREATE POLICY membership_isolation ON memberships
        FOR ALL
        USING (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
        WITH CHECK (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
    """)

    # API Keys: Workspace-scoped access
    op.execute("""
        CREATE POLICY api_key_isolation ON api_keys
        FOR ALL
        USING (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
        WITH CHECK (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
    """)

    # Workspace Resources: Workspace-scoped access
    op.execute("""
        CREATE POLICY workspace_resource_isolation ON workspace_resources
        FOR ALL
        USING (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
        WITH CHECK (
            workspace_id::text = COALESCE(current_setting('app.workspace_id', true), '')
        )
    """)


def downgrade() -> None:
    """Drop all tables and remove RLS."""

    # Drop policies
    op.execute(
        "DROP POLICY IF EXISTS workspace_resource_isolation ON workspace_resources"
    )
    op.execute("DROP POLICY IF EXISTS api_key_isolation ON api_keys")
    op.execute("DROP POLICY IF EXISTS membership_isolation ON memberships")
    op.execute("DROP POLICY IF EXISTS workspace_isolation ON workspaces")

    # Disable RLS
    op.execute("ALTER TABLE IF EXISTS workspace_resources DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS api_keys DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS memberships DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS workspaces DISABLE ROW LEVEL SECURITY")

    # Drop tables (in reverse order of creation due to FK constraints)
    op.drop_table("workspace_resources")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # Drop enum type
    membership_role = postgresql.ENUM(
        "owner", "admin", "member", name="membership_role"
    )
    membership_role.drop(op.get_bind(), checkfirst=True)
