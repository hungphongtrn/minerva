"""Application settings with environment-backed defaults."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database - supports PostgreSQL (production) or SQLite (testing)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/picoclaw"

    # Application
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Sandbox Configuration
    SANDBOX_PROFILE: str = "local_compose"
    """Sandbox provider profile: 'local_compose' or 'daytona'."""

    # Daytona Provider Configuration (used when SANDBOX_PROFILE=daytona)
    DAYTONA_API_TOKEN: str = ""
    """Daytona API token for Cloud or self-hosted authentication."""

    DAYTONA_BASE_URL: str = ""
    """Daytona API base URL. Leave empty for Daytona Cloud.

    Set to self-hosted Daytona URL (e.g., 'https://daytona.example.com/v1')
    for BYOC mode. Empty value defaults to Daytona Cloud.
    """

    DAYTONA_TARGET_REGION: str = "us"
    """Target region for Daytona Cloud workspaces (default: 'us')."""


# Global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get database URL, falling back to SQLite for testing if PostgreSQL is unavailable."""
    return settings.DATABASE_URL
