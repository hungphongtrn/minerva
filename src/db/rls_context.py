"""Row Level Security (RLS) context management.

Provides transaction-scoped database context for tenant isolation.
Sets Postgres session configuration that RLS policies use to
enforce workspace boundaries.

Usage:
    from src.db.rls_context import RLSContext, with_rls_context

    # Method 1: Context manager
    with RLSContext(db, workspace_id, user_id, role):
        # All queries within this block use the RLS context
        resources = db.query(WorkspaceResource).all()

    # Method 2: Dependency injection
    @router.get("/resources")
    async def list_resources(
        db: Session = Depends(get_db),
        principal: Principal = Depends(resolve_principal)
    ):
        with_rls_context(db, principal.workspace_id, principal.user_id, principal.role)
        return db.query(WorkspaceResource).all()
"""

from contextlib import contextmanager
from typing import Optional, Generator
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text


class RLSContext:
    """Transaction-scoped RLS context manager.

    Sets Postgres session configuration that RLS policies use.
    The settings are automatically cleared when the transaction ends
    or the context manager exits.

    Setting names:
    - app.workspace_id: The workspace ID for tenant filtering
    - app.user_id: The user ID for audit/ownership checks
    - app.role: The user's role for permission checks
    """

    # Configuration setting names used by RLS policies
    WORKSPACE_ID_KEY = "app.workspace_id"
    USER_ID_KEY = "app.user_id"
    ROLE_KEY = "app.role"

    def __init__(
        self,
        db: Session,
        workspace_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        role: Optional[str] = None,
    ):
        """Initialize RLS context.

        Args:
            db: SQLAlchemy session
            workspace_id: Workspace ID for tenant boundary
            user_id: User ID for audit/ownership
            role: User role (owner, admin, member)
        """
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.role = role

    def set_context(self) -> None:
        """Set the RLS context in the current database session.

        This executes SELECT set_config() calls that RLS policies reference.
        Settings are transaction-local (is_local=true) for automatic cleanup.
        """
        if self.workspace_id:
            self._set_config(self.WORKSPACE_ID_KEY, str(self.workspace_id))
        if self.user_id:
            self._set_config(self.USER_ID_KEY, str(self.user_id))
        if self.role:
            self._set_config(self.ROLE_KEY, self.role)

    def clear_context(self) -> None:
        """Clear the RLS context from the current database session.

        This resets all app.* settings to NULL.
        """
        self._set_config(self.WORKSPACE_ID_KEY, None)
        self._set_config(self.USER_ID_KEY, None)
        self._set_config(self.ROLE_KEY, None)

    def _set_config(self, key: str, value: Optional[str]) -> None:
        """Execute set_config for a single setting.

        Uses PostgreSQL set_config() function with is_local=true for
        transaction-scoped settings. For non-PostgreSQL backends,
        the call is silently ignored to allow test compatibility.

        Args:
            key: The configuration key (e.g., app.workspace_id)
            value: The value to set, or None to reset
        """
        # Check if we're on PostgreSQL - silently skip for other dialects
        # This allows tests to run on SQLite without RLS errors
        # For mock objects or unknown dialects, assume PostgreSQL (execute the SQL)
        try:
            dialect_name = self.db.bind.dialect.name
            # Only skip for explicitly non-PostgreSQL dialects (string comparison)
            if isinstance(dialect_name, str) and dialect_name != "postgresql":
                return
        except AttributeError:
            # Mock objects or incomplete db session - proceed with SQL execution
            pass

        # PostgreSQL: Use SELECT set_config(key, value, is_local)
        # is_local=true makes the setting transaction-scoped
        if value is not None:
            stmt = text("SELECT set_config(:key, :value, true)")
            self.db.execute(stmt, {"key": key, "value": value})
        else:
            # Reset the config key to NULL (transaction-local)
            stmt = text("SELECT set_config(:key, NULL, true)")
            self.db.execute(stmt, {"key": key})

    def __enter__(self) -> "RLSContext":
        """Enter context manager - set RLS context."""
        self.set_context()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager - clear RLS context."""
        self.clear_context()


@contextmanager
def with_rls_context(
    db: Session,
    workspace_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    role: Optional[str] = None,
) -> Generator[None, None, None]:
    """Context manager for RLS-scoped database operations.

    Usage:
        with with_rls_context(db, workspace_id, user_id, role):
            # All queries here use RLS context
            resources = db.query(WorkspaceResource).all()

    Args:
        db: SQLAlchemy session
        workspace_id: Workspace ID for tenant boundary
        user_id: User ID for audit/ownership
        role: User role (owner, admin, member)

    Yields:
        None (use the same db session)
    """
    context = RLSContext(db, workspace_id, user_id, role)
    context.set_context()
    try:
        yield
    finally:
        context.clear_context()


def set_rls_context(
    db: Session,
    workspace_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    role: Optional[str] = None,
) -> None:
    """Set RLS context without context manager.

    Use this when you need to set context once for an entire request.
    Note: You must manually clear context or it persists for the transaction.

    Args:
        db: SQLAlchemy session
        workspace_id: Workspace ID for tenant boundary
        user_id: User ID for audit/ownership
        role: User role (owner, admin, member)
    """
    context = RLSContext(db, workspace_id, user_id, role)
    context.set_context()


def clear_rls_context(db: Session) -> None:
    """Clear RLS context from the current session.

    Args:
        db: SQLAlchemy session
    """
    context = RLSContext(db)
    context.clear_context()


def get_rls_context(db: Session) -> dict:
    """Get current RLS context from the database session.

    Args:
        db: SQLAlchemy session

    Returns:
        Dictionary with current workspace_id, user_id, role values
    """
    result = {}

    for key in [
        RLSContext.WORKSPACE_ID_KEY,
        RLSContext.USER_ID_KEY,
        RLSContext.ROLE_KEY,
    ]:
        try:
            stmt = text("SELECT current_setting(:key, true)")
            row = db.execute(stmt, {"key": key}).fetchone()
            result[key] = row[0] if row else None
        except Exception:
            result[key] = None

    return result


class RLSRequiredError(Exception):
    """Raised when RLS context is required but not set."""

    pass


def require_rls_context(db: Session, require_workspace: bool = True) -> dict:
    """Verify RLS context is properly set.

    Args:
        db: SQLAlchemy session
        require_workspace: If True, require workspace_id to be set

    Returns:
        Current RLS context dictionary

    Raises:
        RLSRequiredError: If required context is missing
    """
    context = get_rls_context(db)

    if require_workspace and not context.get(RLSContext.WORKSPACE_ID_KEY):
        raise RLSRequiredError("RLS context required: workspace_id not set")

    return context
