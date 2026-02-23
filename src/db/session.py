"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config.settings import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI route handlers to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
