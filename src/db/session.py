"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config.settings import settings

# Base class for ORM models
Base = declarative_base()

# Engine cache for lazy initialization
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create SQLAlchemy engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            future=True,
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
