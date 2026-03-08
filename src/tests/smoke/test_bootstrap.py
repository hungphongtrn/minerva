"""Smoke tests for application bootstrap and basic connectivity."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.db.session import get_engine, get_session_factory
from src.config.settings import settings


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


class TestAppBootstrap:
    """Test that the application can boot successfully."""

    def test_app_imports_without_errors(self):
        """Verify the FastAPI app can be imported."""
        from src.main import app

        assert app is not None
        assert app.title == "Picoclaw API"

    def test_health_endpoint_returns_ok(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_api_root_endpoint(self, client):
        """API root returns expected message."""
        response = client.get("/api/v1/")
        assert response.status_code == 200
        assert response.json() == {"message": "Picoclaw API v1"}


class TestDatabaseBootstrap:
    """Test that database configuration is valid."""

    def test_settings_load_database_url(self):
        """Settings load DATABASE_URL from environment."""
        assert settings.DATABASE_URL is not None
        assert len(settings.DATABASE_URL) > 0

    def test_database_engine_can_be_created(self):
        """Database engine can be instantiated lazily."""
        # This should not raise an exception
        engine = get_engine()
        assert engine is not None
        # Verify engine URL is set (password may be masked in string representation)
        engine_url_str = str(engine.url)
        assert engine_url_str.startswith("postgresql+psycopg://")
        assert "@localhost:5432/picoclaw" in engine_url_str

    def test_session_factory_can_be_created(self):
        """Session factory can be created."""
        Session = get_session_factory()
        assert Session is not None

    def test_models_metadata_contains_expected_tables(self):
        """SQLAlchemy metadata contains all expected tables."""
        from src.db.session import Base

        expected_tables = {
            "users",
            "workspaces",
            "memberships",
            "api_keys",
            "workspace_resources",
        }

        actual_tables = set(Base.metadata.tables.keys())
        assert expected_tables.issubset(actual_tables), (
            f"Missing tables: {expected_tables - actual_tables}"
        )


class TestAlembicConfiguration:
    """Test Alembic migration setup."""

    def test_alembic_env_file_exists(self):
        """Alembic env.py file exists."""
        import os

        env_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "src",
            "db",
            "migrations",
            "env.py",
        )
        assert os.path.exists(env_path), f"env.py not found: {env_path}"

    def test_migration_file_exists(self):
        """Initial migration file exists with RLS configuration."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "src",
            "db",
            "migrations",
            "versions",
            "0001_identity_policy_baseline.py",
        )
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"

    def test_migration_contains_rls_statements(self):
        """Migration contains RLS ENABLE and FORCE statements."""
        import inspect
        import importlib

        # Import migration module dynamically
        migration = importlib.import_module(
            "src.db.migrations.versions.0001_identity_policy_baseline"
        )

        source = inspect.getsource(migration.upgrade)

        # Check for ENABLE ROW LEVEL SECURITY
        assert "ENABLE ROW LEVEL SECURITY" in source, "Migration missing ENABLE ROW LEVEL SECURITY"

        # Check for FORCE ROW LEVEL SECURITY
        assert "FORCE ROW LEVEL SECURITY" in source, "Migration missing FORCE ROW LEVEL SECURITY"

        source = inspect.getsource(migration.upgrade)

        # Check for ENABLE ROW LEVEL SECURITY
        assert "ENABLE ROW LEVEL SECURITY" in source, "Migration missing ENABLE ROW LEVEL SECURITY"

        # Check for FORCE ROW LEVEL SECURITY
        assert "FORCE ROW LEVEL SECURITY" in source, "Migration missing FORCE ROW LEVEL SECURITY"


class TestConfiguration:
    """Test application configuration."""

    def test_debug_flag_defaults_to_false(self):
        """DEBUG defaults to False for safety."""
        assert settings.DEBUG is False

    def test_api_prefix_configured(self):
        """API v1 prefix is configured."""
        assert settings.API_V1_PREFIX == "/api/v1"
