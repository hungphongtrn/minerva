"""Database session management.

Provides request-scoped database sessions with transaction boundaries
and lock-wait safeguards for contention handling.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config.settings import settings

# Base class for ORM models
Base = declarative_base()

# Engine cache for lazy initialization
_engine = None
_SessionLocal = None

# Default lock timeout in seconds (prevents indefinite waits)
DEFAULT_LOCK_TIMEOUT_SECONDS = 5


def get_engine():
    """Get or create SQLAlchemy engine (lazy initialization).

    Configures engine with database-specific lock timeout safeguards
    to prevent indefinite waits during concurrent lease acquisition.
    """
    global _engine
    if _engine is None:
        connect_args = {}

        # Configure lock timeouts based on database type
        if settings.DATABASE_URL.startswith("sqlite"):
            # SQLite: Use busy_timeout (milliseconds)
            connect_args["timeout"] = DEFAULT_LOCK_TIMEOUT_SECONDS
        elif settings.DATABASE_URL.startswith("postgresql"):
            # PostgreSQL: Set lock_timeout (will apply per connection)
            # Note: We use connect_args with options for PostgreSQL
            connect_args["connect_timeout"] = DEFAULT_LOCK_TIMEOUT_SECONDS

        _engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            future=True,
            connect_args=connect_args,
        )

        # Set PostgreSQL lock timeout via event listener for each connection
        if settings.DATABASE_URL.startswith("postgresql"):

            @event.listens_for(_engine, "connect")
            def set_pg_lock_timeout(dbapi_conn, connection_record):
                """Set lock timeout on PostgreSQL connections."""
                with dbapi_conn.cursor() as cursor:
                    cursor.execute(
                        f"SET lock_timeout = '{DEFAULT_LOCK_TIMEOUT_SECONDS}s'"
                    )

    return _engine


def get_session_factory():
    """Get or create session factory (lazy initialization)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


# Backward compatibility - these will work when engine is available
engine = property(get_engine)
SessionLocal = property(get_session_factory)


def get_db():
    """Dependency for FastAPI route handlers to get DB session.

    Provides request-scoped transaction boundaries:
    - Commits on successful request completion
    - Rolls back on raised exceptions
    - Ensures durable persistence across request boundaries
    """
    Session = get_session_factory()
    db = Session()
    try:
        yield db
        # Commit on successful completion (no exception raised)
        db.commit()
    except Exception:
        # Rollback on any exception before re-raising
        db.rollback()
        raise
    finally:
        db.close()
