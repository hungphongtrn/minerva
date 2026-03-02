"""minerva init - Initialize environment and run preflight checks."""

import argparse
import sys
from pathlib import Path


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the init subcommand parser."""
    parser = subparsers.add_parser(
        "init",
        help="Initialize environment and run preflight checks",
        description="Regenerate .env.example and run preflight validation checks",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .env.example without prompting",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed check information",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the init command.

    1. Regenerate .env.example with all documented env vars
    2. Run preflight checks
    3. Exit non-zero if any BLOCKING failures
    """
    # Regenerate .env.example
    _generate_env_example(args.force)

    # Run preflight checks
    from src.services.preflight_service import PreflightService, format_checklist

    service = PreflightService()
    result = service.run_all_checks()

    # Print checklist
    print(format_checklist(result, verbose=args.verbose))

    # Exit non-zero on blocking failures
    if not result.is_healthy:
        print("\n❌ Preflight failed: Fix BLOCKING issues before proceeding", file=sys.stderr)
        return 1

    print("\n✅ Preflight passed: Environment ready")
    return 0


def _generate_env_example(force: bool) -> None:
    """Generate .env.example with all documented env vars grouped by service."""
    env_path = Path(".env.example")

    if env_path.exists() and not force:
        print(".env.example already exists (use --force to overwrite)")
        return

    content = """# Minerva Environment Configuration
# Copy this file to .env and customize as needed

# =============================================================================
# DATABASE - PostgreSQL Configuration
# =============================================================================

# Database credentials (used by docker-compose.yml)
POSTGRES_DB=picoclaw
POSTGRES_USER=picoclaw
POSTGRES_PASSWORD=picoclaw_dev
POSTGRES_PORT=5432

# Connection URL for application (SQLAlchemy + psycopg)
DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}

# =============================================================================
# DAYTONA - Sandbox Provider Configuration
# =============================================================================

# Daytona API key for Cloud or self-hosted authentication (SDK v2)
# Required: Set this to your Daytona API key
DAYTONA_API_KEY=

# Backward compatibility (deprecated, use DAYTONA_API_KEY)
DAYTONA_API_TOKEN=

# Daytona API URL for self-hosted (leave empty for Daytona Cloud)
# Example: https://api.daytona.io
DAYTONA_API_URL=

# Backward compatibility (deprecated, use DAYTONA_API_URL)
DAYTONA_BASE_URL=

# Target region for Daytona Cloud workspaces (default: 'us')
DAYTONA_TARGET=us

# Backward compatibility (deprecated, use DAYTONA_TARGET)
DAYTONA_TARGET_REGION=us

# Base Docker image for Daytona sandboxes
# Production: Use digest-pinned image for determinism
DAYTONA_BASE_IMAGE=daytonaio/workspace-picoclaw:latest

# Strict mode for base image validation (default: false)
# Set to true in production to enforce digest-pinned images
DAYTONA_BASE_IMAGE_STRICT_MODE=false

# Auto-stop interval in seconds (0 = disabled, for runtime continuity)
DAYTONA_AUTO_STOP_INTERVAL=0

# =============================================================================
# PICOCLAW - Snapshot Configuration
# =============================================================================

# Name of the Daytona snapshot to use for sandbox provisioning
# Required for production: Set after running `minerva snapshot build`
DAYTONA_PICOCLAW_SNAPSHOT_NAME=

# =============================================================================
# S3 - Checkpoint Storage Configuration
# =============================================================================

# Enable checkpoint persistence (default: false)
CHECKPOINT_ENABLED=false

# S3 bucket name for checkpoint archives
CHECKPOINT_S3_BUCKET=

# S3-compatible endpoint URL (leave empty for AWS S3)
# Examples:
#   AWS S3: https://s3.us-east-1.amazonaws.com
#   MinIO: http://localhost:9000
CHECKPOINT_S3_ENDPOINT=

# AWS region for S3 bucket (used when ENDPOINT is empty)
CHECKPOINT_S3_REGION=us-east-1

# S3 credentials
CHECKPOINT_S3_ACCESS_KEY=
CHECKPOINT_S3_SECRET_KEY=

# Checkpoint timing configuration
CHECKPOINT_MILESTONE_INTERVAL_SECONDS=300
CHECKPOINT_SAFETY_MARGIN_BYTES=104857600

# =============================================================================
# LLM - Language Model Configuration
# =============================================================================

# LLM API key (supports OpenAI and compatible APIs)
LLM_API_KEY=

# LLM API base URL (leave empty for default)
LLM_API_BASE=

# LLM model name
LLM_MODEL=

# =============================================================================
# OBSERVABILITY - Logging and Metrics
# =============================================================================

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Enable Prometheus metrics endpoint
PROMETHEUS_ENABLED=false

# =============================================================================
# APPLICATION - General Settings
# =============================================================================

# Debug mode (enables /docs and /redoc endpoints)
DEBUG=false

# Secret key for session signing (change in production)
SECRET_KEY=dev-secret-key-change-in-production

# API version prefix
API_V1_PREFIX=/api/v1

# =============================================================================
# BRIDGE - Picoclaw Gateway Configuration
# =============================================================================

# Bridge authentication token (set per-sandbox)
PICOCLAW_BRIDGE_TOKEN=

# Bridge configuration (JSON)
# Example: {"HEALTH_TIMEOUT": 5, "EXECUTE_TIMEOUT": 600}
PICOCLAW_BRIDGE={}
"""

    env_path.write_text(content)
    print(f"Generated {env_path}")
