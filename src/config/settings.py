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

    # Idle TTL Configuration
    SANDBOX_IDLE_TTL_SECONDS: int = 3600
    """Idle time-to-live in seconds before auto-stopping sandboxes.

    Sandboxes with no activity for longer than this TTL are eligible
    for automatic stop. Minimum: 60 seconds, Maximum: 86400 seconds (24 hours).
    Default: 3600 seconds (1 hour).
    """

    # Daytona Provider Configuration (used when SANDBOX_PROFILE=daytona)
    DAYTONA_API_KEY: str = ""
    """Daytona API key for Cloud or self-hosted authentication (SDK v2)."""

    DAYTONA_API_TOKEN: str = ""
    """Deprecated: Use DAYTONA_API_KEY instead. Backward compatibility."""

    DAYTONA_API_URL: str = ""
    """Daytona API URL. Leave empty for Daytona Cloud (SDK v2).

    Set to self-hosted Daytona URL (e.g., 'https://api.daytona.io')
    for BYOC mode. Empty value defaults to Daytona Cloud.
    """

    DAYTONA_BASE_URL: str = ""
    """Deprecated: Use DAYTONA_API_URL instead. Backward compatibility."""

    DAYTONA_TARGET: str = "us"
    """Target region for Daytona Cloud workspaces (default: 'us') (SDK v2)."""

    DAYTONA_TARGET_REGION: str = "us"
    """Deprecated: Use DAYTONA_TARGET instead. Backward compatibility."""


# Global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get database URL, falling back to SQLite for testing if PostgreSQL is unavailable."""
    return settings.DATABASE_URL
