"""Preflight validation service for environment and dependency checks.

Provides deterministic checklist output for CLI commands with severity-based
handling of required vs optional dependencies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config.settings import settings


class CheckSeverity(str, Enum):
    """Severity level for preflight checks."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


class CheckStatus(str, Enum):
    """Status of a preflight check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class PreflightCheck:
    """Single preflight check result."""

    code: str
    """Machine-readable code for programmatic handling."""
    service: str
    """Service category: database, daytona, s3, llm, observability."""
    severity: CheckSeverity
    """Severity: BLOCKING (must pass), WARNING (optional), INFO."""
    status: CheckStatus
    """Result: PASS, FAIL, SKIP."""
    message: str
    """Human-readable status message."""
    remediation: str
    """Actionable guidance when check fails."""
    details: dict[str, Any] = field(default_factory=dict)
    """Additional context for debugging."""


@dataclass
class PreflightResult:
    """Complete preflight validation result."""

    checks: list[PreflightCheck]
    """All checks performed."""
    blocking_failures: int
    """Count of BLOCKING severity failures."""
    warnings: int
    """Count of WARNING severity failures."""

    @property
    def is_healthy(self) -> bool:
        """True if no BLOCKING failures."""
        return self.blocking_failures == 0


class PreflightService:
    """Service for running environment preflight checks.

    All checks are lazy - no network calls at import time.
    Checks are only performed when explicitly invoked.
    """

    def __init__(self, db_engine: Engine | None = None):
        """Initialize preflight service.

        Args:
            db_engine: Optional SQLAlchemy engine for database checks.
                      If not provided, a new engine will be created.
        """
        self._db_engine = db_engine

    def run_all_checks(self) -> PreflightResult:
        """Run all preflight checks and return aggregated result."""
        checks = [
            # Required (BLOCKING)
            self._check_database(),
            self._check_daytona_auth(),
            self._check_workspace_configured(),
            # Optional (WARNING)
            self._check_s3_config(),
            self._check_llm_config(),
            self._check_picoclaw_snapshot(),
            # Info
            self._check_observability(),
        ]

        blocking_failures = sum(
            1
            for c in checks
            if c.severity == CheckSeverity.BLOCKING and c.status == CheckStatus.FAIL
        )
        warnings = sum(
            1
            for c in checks
            if c.severity == CheckSeverity.WARNING and c.status == CheckStatus.FAIL
        )

        return PreflightResult(
            checks=checks,
            blocking_failures=blocking_failures,
            warnings=warnings,
        )

    def check_database_schema_current(self) -> PreflightCheck:
        """Check if database schema is at Alembic head revision.

        This is a specialized check used by `minerva serve` to enforce
        the "never auto-migrate" contract.
        """
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)

            # Get head revision
            head_rev = script.get_current_head()

            # Get current database revision
            engine = self._get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.fetchone()
                current_rev = row[0] if row else None

            if current_rev == head_rev:
                return PreflightCheck(
                    code="DB_SCHEMA_CURRENT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message=f"Database schema at head revision: {current_rev}",
                    remediation="",
                    details={"current": current_rev, "head": head_rev},
                )
            else:
                return PreflightCheck(
                    code="DB_SCHEMA_CURRENT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message=f"Database schema behind: current={current_rev}, head={head_rev}",
                    remediation="run `minerva migrate`",
                    details={"current": current_rev, "head": head_rev},
                )
        except Exception as e:
            return PreflightCheck(
                code="DB_SCHEMA_CURRENT",
                service="database",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message=f"Failed to check schema version: {e}",
                remediation="Ensure database is accessible and alembic.ini is configured",
                details={"error": str(e)},
            )

    def check_picoclaw_snapshot_exists(self) -> PreflightCheck:
        """Check if the configured Picoclaw Daytona snapshot exists.

        This is a specialized check used by `minerva serve` to enforce
        the snapshot gate before starting the server.
        """
        snapshot_name = self._get_picoclaw_snapshot_name()
        if not snapshot_name:
            return PreflightCheck(
                code="PICOCLAW_SNAPSHOT",
                service="daytona",
                severity=CheckSeverity.WARNING,
                status=CheckStatus.SKIP,
                message="No Picoclaw snapshot configured (DAYTONA_PICOCLAW_SNAPSHOT_NAME not set)",
                remediation="Set DAYTONA_PICOCLAW_SNAPSHOT_NAME env var or run `minerva snapshot build`",
                details={},
            )

        # Check if snapshot exists via Daytona API
        try:
            from daytona import AsyncDaytona, DaytonaConfig

            # Use sync wrapper for CLI simplicity
            import asyncio

            async def _check() -> bool:
                api_key = settings.DAYTONA_API_KEY or settings.DAYTONA_API_TOKEN
                api_url = settings.DAYTONA_API_URL or settings.DAYTONA_BASE_URL
                target = settings.DAYTONA_TARGET or settings.DAYTONA_TARGET_REGION

                config = DaytonaConfig(
                    api_key=api_key,
                    api_url=api_url,
                    target=target,
                )
                async with AsyncDaytona(config) as client:
                    snapshots = await client.snapshot.list()
                    return any(s.name == snapshot_name for s in snapshots)

            exists = asyncio.run(_check())

            if exists:
                return PreflightCheck(
                    code="PICOCLAW_SNAPSHOT",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message=f"Picoclaw snapshot '{snapshot_name}' exists",
                    remediation="",
                    details={"snapshot_name": snapshot_name},
                )
            else:
                return PreflightCheck(
                    code="PICOCLAW_SNAPSHOT",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message=f"Picoclaw snapshot '{snapshot_name}' not found",
                    remediation="run `minerva snapshot build`",
                    details={"snapshot_name": snapshot_name},
                )
        except Exception as e:
            return PreflightCheck(
                code="PICOCLAW_SNAPSHOT",
                service="daytona",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message=f"Failed to check snapshot: {e}",
                remediation="Ensure Daytona credentials are configured and accessible",
                details={"error": str(e), "snapshot_name": snapshot_name},
            )

    def _check_database(self) -> PreflightCheck:
        """Check database connectivity."""
        try:
            engine = self._get_db_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return PreflightCheck(
                code="DB_CONNECT",
                service="database",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.PASS,
                message="Database connection successful",
                remediation="",
                details={"url": self._mask_url(settings.DATABASE_URL)},
            )
        except Exception as e:
            return PreflightCheck(
                code="DB_CONNECT",
                service="database",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message=f"Database connection failed: {e}",
                remediation="Ensure PostgreSQL is running and DATABASE_URL is configured",
                details={"error": str(e)},
            )

    def _check_daytona_auth(self) -> PreflightCheck:
        """Check Daytona authentication credentials."""
        api_key = settings.DAYTONA_API_KEY or settings.DAYTONA_API_TOKEN
        if not api_key:
            return PreflightCheck(
                code="DAYTONA_AUTH",
                service="daytona",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message="Daytona API key not configured",
                remediation="Set DAYTONA_API_KEY env var (or DAYTONA_API_TOKEN for backward compat)",
                details={},
            )

        # Basic validation - actual connectivity tested when needed
        return PreflightCheck(
            code="DAYTONA_AUTH",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="Daytona API key configured",
            remediation="",
            details={"api_url": settings.DAYTONA_API_URL or "Daytona Cloud"},
        )

    def _check_workspace_configured(self) -> PreflightCheck:
        """Check MINERVA_WORKSPACE_ID is configured and workspace has registered packs.

        This is required for OSS mode where end-user requests are resolved
        to the developer's workspace.
        """
        if not settings.MINERVA_WORKSPACE_ID:
            return PreflightCheck(
                code="WORKSPACE_CONFIGURED",
                service="oss",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message="MINERVA_WORKSPACE_ID not configured",
                remediation="Set MINERVA_WORKSPACE_ID. Run `minerva register` to get your workspace ID.",
                details={},
            )

        # Validate workspace exists and has packs
        try:
            engine = self._get_db_engine()
            with engine.connect() as conn:
                # Check workspace exists
                result = conn.execute(
                    text("SELECT id, name FROM workspaces WHERE id = :workspace_id"),
                    {"workspace_id": settings.MINERVA_WORKSPACE_ID},
                )
                workspace_row = result.fetchone()

                if not workspace_row:
                    return PreflightCheck(
                        code="WORKSPACE_CONFIGURED",
                        service="oss",
                        severity=CheckSeverity.BLOCKING,
                        status=CheckStatus.FAIL,
                        message=f"Workspace '{settings.MINERVA_WORKSPACE_ID}' not found in database",
                        remediation="Run `minerva register` to create your workspace, then set MINERVA_WORKSPACE_ID.",
                        details={"workspace_id": settings.MINERVA_WORKSPACE_ID},
                    )

                # Check workspace has registered agent packs
                result = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM agent_packs WHERE workspace_id = :workspace_id AND is_active = true"
                    ),
                    {"workspace_id": settings.MINERVA_WORKSPACE_ID},
                )
                pack_count = result.scalar()

                if pack_count == 0:
                    return PreflightCheck(
                        code="WORKSPACE_CONFIGURED",
                        service="oss",
                        severity=CheckSeverity.BLOCKING,
                        status=CheckStatus.FAIL,
                        message="Workspace has no registered agent packs",
                        remediation="Run `minerva register` first to register an agent pack.",
                        details={"workspace_id": settings.MINERVA_WORKSPACE_ID},
                    )

                if pack_count > 1:
                    return PreflightCheck(
                        code="WORKSPACE_CONFIGURED",
                        service="oss",
                        severity=CheckSeverity.WARNING,
                        status=CheckStatus.PASS,
                        message=f"Workspace has {pack_count} agent packs. OSS mode supports one pack per workspace.",
                        remediation="Using first registered pack. Remove extra packs for clean OSS deployment.",
                        details={
                            "workspace_id": settings.MINERVA_WORKSPACE_ID,
                            "pack_count": pack_count,
                        },
                    )

                return PreflightCheck(
                    code="WORKSPACE_CONFIGURED",
                    service="oss",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message=f"Workspace '{workspace_row[1]}' configured with {pack_count} agent pack(s)",
                    remediation="",
                    details={
                        "workspace_id": settings.MINERVA_WORKSPACE_ID,
                        "pack_count": pack_count,
                    },
                )

        except Exception as e:
            return PreflightCheck(
                code="WORKSPACE_CONFIGURED",
                service="oss",
                severity=CheckSeverity.BLOCKING,
                status=CheckStatus.FAIL,
                message=f"Failed to validate workspace: {e}",
                remediation="Ensure database is accessible and workspace exists",
                details={
                    "workspace_id": settings.MINERVA_WORKSPACE_ID,
                    "error": str(e),
                },
            )

    def _check_s3_config(self) -> PreflightCheck:
        """Check S3 checkpoint storage configuration (optional)."""
        if not settings.CHECKPOINT_S3_BUCKET:
            return PreflightCheck(
                code="S3_CONFIG",
                service="s3",
                severity=CheckSeverity.WARNING,
                status=CheckStatus.SKIP,
                message="S3 checkpoint storage not configured",
                remediation="Set CHECKPOINT_S3_* vars for checkpoint persistence",
                details={},
            )

        # Check required S3 credentials
        missing = []
        if not settings.CHECKPOINT_S3_ACCESS_KEY:
            missing.append("CHECKPOINT_S3_ACCESS_KEY")
        if not settings.CHECKPOINT_S3_SECRET_KEY:
            missing.append("CHECKPOINT_S3_SECRET_KEY")

        if missing:
            return PreflightCheck(
                code="S3_CONFIG",
                service="s3",
                severity=CheckSeverity.WARNING,
                status=CheckStatus.FAIL,
                message=f"S3 bucket configured but missing: {', '.join(missing)}",
                remediation="Set all CHECKPOINT_S3_* environment variables",
                details={"bucket": settings.CHECKPOINT_S3_BUCKET, "missing": missing},
            )

        return PreflightCheck(
            code="S3_CONFIG",
            service="s3",
            severity=CheckSeverity.WARNING,
            status=CheckStatus.PASS,
            message="S3 checkpoint storage configured",
            remediation="",
            details={"bucket": settings.CHECKPOINT_S3_BUCKET},
        )

    def _check_llm_config(self) -> PreflightCheck:
        """Check LLM configuration (optional)."""
        # Check for common LLM env vars via settings (reads from .env file)
        llm_api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        llm_api_base = settings.LLM_API_BASE or settings.OPENAI_API_BASE
        llm_model = settings.LLM_MODEL or settings.OPENAI_MODEL

        if not llm_api_key:
            return PreflightCheck(
                code="LLM_CONFIG",
                service="llm",
                severity=CheckSeverity.WARNING,
                status=CheckStatus.SKIP,
                message="LLM API key not configured",
                remediation="Set LLM_API_KEY or OPENAI_API_KEY for agent LLM access",
                details={},
            )

        return PreflightCheck(
            code="LLM_CONFIG",
            service="llm",
            severity=CheckSeverity.WARNING,
            status=CheckStatus.PASS,
            message="LLM API key configured",
            remediation="",
            details={
                "api_base": llm_api_base or "default",
                "model": llm_model or "default",
            },
        )

    def _check_picoclaw_snapshot(self) -> PreflightCheck:
        """Check Picoclaw snapshot configuration (optional for init, blocking for serve)."""
        snapshot_name = self._get_picoclaw_snapshot_name()
        if not snapshot_name:
            return PreflightCheck(
                code="PICOCLAW_SNAPSHOT_CONFIG",
                service="daytona",
                severity=CheckSeverity.WARNING,
                status=CheckStatus.SKIP,
                message="Picoclaw snapshot name not configured",
                remediation="Set DAYTONA_PICOCLAW_SNAPSHOT_NAME for production sandbox provisioning",
                details={},
            )

        return PreflightCheck(
            code="PICOCLAW_SNAPSHOT_CONFIG",
            service="daytona",
            severity=CheckSeverity.WARNING,
            status=CheckStatus.PASS,
            message=f"Picoclaw snapshot configured: {snapshot_name}",
            remediation="",
            details={"snapshot_name": snapshot_name},
        )

    def _check_observability(self) -> PreflightCheck:
        """Check observability configuration."""
        # Check for common observability env vars
        import os

        prometheus_enabled = os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true"
        log_level = os.getenv("LOG_LEVEL", "INFO")

        details = {
            "prometheus_enabled": prometheus_enabled,
            "log_level": log_level,
        }

        return PreflightCheck(
            code="OBSERVABILITY",
            service="observability",
            severity=CheckSeverity.INFO,
            status=CheckStatus.PASS,
            message=f"Observability: prometheus={prometheus_enabled}, log_level={log_level}",
            remediation="",
            details=details,
        )

    def _get_db_engine(self) -> Engine:
        """Get or create database engine."""
        if self._db_engine is None:
            from sqlalchemy import create_engine

            self._db_engine = create_engine(settings.DATABASE_URL)
        return self._db_engine

    def _get_picoclaw_snapshot_name(self) -> str | None:
        """Get Picoclaw snapshot name from environment."""
        return settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME or None

    def _mask_url(self, url: str) -> str:
        """Mask credentials in URL for safe logging."""
        import re

        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


def format_checklist(result: PreflightResult, verbose: bool = False) -> str:
    """Format preflight result as human-readable checklist.

    Args:
        result: Preflight result to format.
        verbose: Include details in output.

    Returns:
        Formatted checklist string.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("MINERVA PREFLIGHT CHECKLIST")
    lines.append("=" * 60)

    for check in result.checks:
        # Status indicator
        if check.status == CheckStatus.PASS:
            status_icon = "✓"
        elif check.status == CheckStatus.SKIP:
            status_icon = "○"
        else:
            status_icon = "✗"

        # Severity indicator
        severity_str = f"[{check.severity.value}]"
        status_str = f"[{check.status.value}]"

        lines.append(
            f"\n{status_icon} {check.code:<25} {severity_str:<12} {status_str}"
        )
        lines.append(f"  {check.message}")

        if check.status == CheckStatus.FAIL and check.remediation:
            lines.append(f"  → {check.remediation}")

        if verbose and check.details:
            for key, value in check.details.items():
                lines.append(f"    {key}: {value}")

    lines.append("\n" + "=" * 60)
    lines.append(
        f"SUMMARY: {result.blocking_failures} blocking, {result.warnings} warnings"
    )
    lines.append("=" * 60)

    return "\n".join(lines)
