"""Smoke test fixtures for database schema validation.

Provides minimal fixtures for smoke testing database schema and migrations.
"""

import pytest
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from src.db.session import Base


@pytest.fixture(scope="function")
def db_engine(tmp_path):
    """Create a file-based SQLite database engine for tests.

    Note: Some schema tests require PostgreSQL-specific features (enums).
    Those tests are skipped when running on SQLite.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()

    # Enable foreign key support for SQLite
    session.execute(text("PRAGMA foreign_keys=ON"))
    session.commit()

    yield session

    session.rollback()
    session.close()
