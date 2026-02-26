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

    # Daytona Image Configuration (for production registry images)
    DAYTONA_BASE_IMAGE: str = "daytonaio/workspace-picoclaw:latest"
    """Base Docker image for Daytona sandboxes (default: daytonaio/workspace-picoclaw:latest).
    
    In production, this should point to a Picoclaw-specific image with
    identity files (AGENT.md, SOUL.md, IDENTITY.md) and skills/ pre-installed.
    """

    DAYTONA_AUTO_STOP_INTERVAL: int = 0
    """Auto-stop interval in seconds (default: 0).
    
    0 disables auto-stop for runtime continuity. Set to positive value
    for automatic cleanup after inactivity (minimum: 60 seconds).
    """

    # Picoclaw Bridge Configuration
    PICOCLAW_BRIDGE_TOKEN: str = ""
    """Bearer token for Picoclaw gateway authentication.
    
    Set per-sandbox via environment variable. Leave empty for development.
    """

    # Bridge Configuration (accessed as PICOCLAW_BRIDGE dict)
    PICOCLAW_BRIDGE: dict = {}
    """Bridge timeout/retry/auth configuration.

    Supports nested configuration:
    - HEALTH_TIMEOUT: seconds (default: 10)
    - HEALTH_RETRIES: count (default: 3)
    - HEALTH_BACKOFF: seconds (default: 1.0)
    - EXECUTE_TIMEOUT: seconds (default: 300)
    - EXECUTE_RETRIES: count (default: 0)

    Example:
        PICOCLAW_BRIDGE='{"HEALTH_TIMEOUT": 5, "EXECUTE_TIMEOUT": 600}'
    """

    # Checkpoint Storage Configuration (S3-compatible)
    CHECKPOINT_S3_BUCKET: str = ""
    """S3 bucket name for checkpoint archives.

    Required for checkpoint persistence in non-guest workspaces.
    Leave empty to disable checkpoint persistence (development mode).
    """

    CHECKPOINT_S3_ENDPOINT: str = ""
    """S3-compatible endpoint URL.

    Examples:
        - AWS S3: "https://s3.us-east-1.amazonaws.com"
        - MinIO: "http://localhost:9000"
        - Ceph: "http://ceph-rgw.local:7480"

    Leave empty to use AWS S3 default endpoint (requires CHECKPOINT_S3_REGION).
    """

    CHECKPOINT_S3_REGION: str = "us-east-1"
    """AWS region for S3 bucket (default: us-east-1).

    Used when CHECKPOINT_S3_ENDPOINT is empty (AWS S3 mode).
    """

    CHECKPOINT_S3_ACCESS_KEY: str = ""
    """S3 access key for checkpoint storage authentication.

    Required when CHECKPOINT_S3_BUCKET is set.
    """

    CHECKPOINT_S3_SECRET_KEY: str = ""
    """S3 secret key for checkpoint storage authentication.

    Required when CHECKPOINT_S3_BUCKET is set.
    """

    CHECKPOINT_MILESTONE_INTERVAL_SECONDS: int = 300
    """Minimum interval between automatic checkpoint milestones (default: 300s / 5 min).

    Prevents checkpoint spam while ensuring reasonable recovery granularity.
    Minimum: 60 seconds, Recommended: 300-600 seconds.
    """

    CHECKPOINT_SAFETY_MARGIN_BYTES: int = 100 * 1024 * 1024  # 100MB
    """Maximum checkpoint size before triggering safety measures (default: 100MB).

    Checkpoints exceeding this size may be rejected or trigger warnings.
    """

    CHECKPOINT_ENABLED: bool = False
    """Global checkpoint persistence toggle (default: False).

    Set to True to enable checkpoint persistence for non-guest workspaces.
    Requires valid CHECKPOINT_S3_* configuration."""


# Global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get database URL, falling back to SQLite for testing if PostgreSQL is unavailable."""
    return settings.DATABASE_URL
