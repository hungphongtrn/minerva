"""Health and readiness endpoints for OSS operator checks.

/health - Returns component health status (always 200, never raises)
/ready - Returns readiness status (200 if ready, 503 if blocking dependencies fail)

Readiness gates (fail-closed):
1. Database connectivity
2. Daytona authentication
3. Configured snapshot exists
4. Schema is at head revision

If any blocking dependency fails, /ready returns 503 with remediation guidance.
"""

from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel

from src.services.preflight_service import (
    PreflightService,
    CheckStatus,
    CheckSeverity,
)

router = APIRouter()


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    status: str
    message: str
    remediation: str | None = None


class HealthResponse(BaseModel):
    """Response for /health endpoint."""

    status: str
    components: dict[str, ComponentHealth]


class ReadinessResponse(BaseModel):
    """Response for /ready endpoint."""

    ready: bool
    status: str
    checks: dict[str, ComponentHealth]
    remediation: str | None = None


def _preflight_service() -> PreflightService:
    """Get PreflightService instance."""
    return PreflightService()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint - returns component statuses.

    This endpoint ALWAYS returns 200, even if components are unhealthy.
    It's designed for monitoring and debugging, not for k8s readiness probes.

    Components checked:
    - database: PostgreSQL connectivity
    - daytona: Daytona API authentication
    - s3: S3 checkpoint storage (optional)
    - llm: LLM API configuration (optional)
    """
    service = _preflight_service()
    result = service.run_all_checks()

    components: dict[str, ComponentHealth] = {}

    for check in result.checks:
        component_name = check.service
        components[component_name] = ComponentHealth(
            status=check.status.value,
            message=check.message,
            remediation=check.remediation if check.remediation else None,
        )

    # Overall status based on blocking failures
    overall_status = "healthy" if result.is_healthy else "degraded"

    return HealthResponse(
        status=overall_status,
        components=components,
    )


@router.get("/ready")
async def readiness_check(response: Response) -> ReadinessResponse:
    """Readiness check endpoint - k8s readiness probe semantics.

    Returns 200 if all blocking dependencies are ready:
    - Database is connected and schema is at head
    - Daytona API is authenticated
    - Configured snapshot exists

    Returns 503 if any blocking dependency fails, with remediation guidance.

    This is fail-closed: missing or failing dependencies result in 503.
    """
    service = _preflight_service()

    # Run basic preflight checks
    preflight_result = service.run_all_checks()

    # Run specialized checks for readiness
    schema_check = service.check_database_schema_current()
    snapshot_check = service.check_picoclaw_snapshot_exists()

    # Collect all checks
    all_checks = list(preflight_result.checks) + [schema_check, snapshot_check]

    # Build response components
    checks: dict[str, ComponentHealth] = {}
    blocking_failures: list[str] = []
    remediation_messages: list[str] = []

    for check in all_checks:
        check_key = f"{check.service}:{check.code}"
        checks[check_key] = ComponentHealth(
            status=check.status.value,
            message=check.message,
            remediation=check.remediation if check.remediation else None,
        )

        # Track blocking failures
        if (
            check.severity == CheckSeverity.BLOCKING
            and check.status == CheckStatus.FAIL
        ):
            blocking_failures.append(check.code)
            if check.remediation:
                remediation_messages.append(check.remediation)

    # Determine readiness
    is_ready = len(blocking_failures) == 0

    if is_ready:
        response.status_code = 200
        return ReadinessResponse(
            ready=True,
            status="ready",
            checks=checks,
            remediation=None,
        )
    else:
        response.status_code = 503
        combined_remediation = "; ".join(remediation_messages) if remediation_messages else None
        return ReadinessResponse(
            ready=False,
            status=f"not_ready:{len(blocking_failures)}_blocking_failures",
            checks=checks,
            remediation=combined_remediation,
        )
