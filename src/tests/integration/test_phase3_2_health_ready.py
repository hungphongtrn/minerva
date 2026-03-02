"""Integration tests for OSS operator endpoints: /health, /ready.

Tests verify:
- /health always returns 200 with component statuses
- /ready returns 200 if blocking deps OK, 503 otherwise (fail-closed)
- Endpoints are at root level (no /api/v1 prefix)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.main import create_app
from src.services.preflight_service import (
    PreflightCheck,
    PreflightResult,
    CheckSeverity,
    CheckStatus,
)


@pytest.fixture
def client():
    """Create test client for integration tests."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_preflight_service():
    """Mock PreflightService for controlled testing."""
    with patch("src.api.oss.routes.health._preflight_service") as mock:
        yield mock


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_200_even_when_unhealthy(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Health endpoint always returns 200, even with failing components."""
        # Setup: all checks fail
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message="Database connection failed",
                    remediation="Check DATABASE_URL",
                )
            ],
            blocking_failures=1,
            warnings=0,
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "database" in data["components"]

    def test_health_returns_healthy_when_all_pass(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Health endpoint returns healthy when all checks pass."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Database connection successful",
                    remediation="",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Daytona API key configured",
                    remediation="",
                ),
            ],
            blocking_failures=0,
            warnings=0,
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_includes_all_components(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Health endpoint includes status for all expected components."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="OK",
                    remediation="",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="OK",
                    remediation="",
                ),
                PreflightCheck(
                    code="S3_CONFIG",
                    service="s3",
                    severity=CheckSeverity.WARNING,
                    status=CheckStatus.SKIP,
                    message="S3 not configured",
                    remediation="",
                ),
                PreflightCheck(
                    code="LLM_CONFIG",
                    service="llm",
                    severity=CheckSeverity.WARNING,
                    status=CheckStatus.SKIP,
                    message="LLM not configured",
                    remediation="",
                ),
            ],
            blocking_failures=0,
            warnings=0,
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        components = data["components"]
        # Should include all component types
        assert "database" in components
        assert "daytona" in components
        assert "s3" in components
        assert "llm" in components


class TestReadyEndpoint:
    """Tests for /ready endpoint (k8s readiness semantics)."""

    def test_ready_returns_200_when_all_blocking_pass(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Ready returns 200 when all blocking dependencies are healthy."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Database OK",
                    remediation="",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Daytona OK",
                    remediation="",
                ),
            ],
            blocking_failures=0,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="Schema at head",
            remediation="",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="Snapshot exists",
            remediation="",
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["status"] == "ready"

    def test_ready_returns_503_on_database_failure(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Ready returns 503 when database fails (fail-closed)."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message="Database connection failed",
                    remediation="Check DATABASE_URL",
                ),
            ],
            blocking_failures=1,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.FAIL,
            message="Cannot check schema",
            remediation="Database not connected",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.SKIP,
            message="Skipped due to earlier failure",
            remediation="",
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert "remediation" in data
        assert data["remediation"] is not None

    def test_ready_returns_503_on_snapshot_missing(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Ready returns 503 when configured snapshot is missing.

        The remediation MUST tell developer to run 'minerva snapshot build'.
        """
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Database OK",
                    remediation="",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Daytona OK",
                    remediation="",
                ),
            ],
            blocking_failures=0,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="Schema at head",
            remediation="",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.FAIL,
            message="Snapshot 'picoclaw-base' not found",
            remediation="run `minerva snapshot build`",
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        # Verify remediation message includes snapshot build command
        assert "minerva snapshot build" in data["remediation"]

    def test_ready_returns_503_on_schema_behind(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Ready returns 503 when database schema is behind head revision."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Database OK",
                    remediation="",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.PASS,
                    message="Daytona OK",
                    remediation="",
                ),
            ],
            blocking_failures=0,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.FAIL,
            message="Schema behind: current=abc123, head=def456",
            remediation="run `minerva migrate`",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="Snapshot exists",
            remediation="",
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False

    def test_ready_includes_remediation_on_failure(
        self, client: TestClient, mock_preflight_service: MagicMock
    ):
        """Ready includes actionable remediation when not ready."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    code="DB_CONNECT",
                    service="database",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message="Connection refused",
                    remediation="Start PostgreSQL",
                ),
                PreflightCheck(
                    code="DAYTONA_AUTH",
                    service="daytona",
                    severity=CheckSeverity.BLOCKING,
                    status=CheckStatus.FAIL,
                    message="API key not set",
                    remediation="Set DAYTONA_API_KEY",
                ),
            ],
            blocking_failures=2,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.FAIL,
            message="Cannot check",
            remediation="Fix database first",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.FAIL,
            message="Snapshot missing",
            remediation="run `minerva snapshot build`",
        )
        mock_preflight_service.return_value = mock_service

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        # Should include combined remediation guidance
        assert data["remediation"] is not None
        assert len(data["remediation"]) > 0


class TestRootLevelEndpoints:
    """Tests verifying endpoints are at root level (no /api/v1 prefix)."""

    def test_health_at_root_level(self, client: TestClient, mock_preflight_service: MagicMock):
        """/health is accessible at root, not under /api/v1."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[],
            blocking_failures=0,
            warnings=0,
        )
        mock_preflight_service.return_value = mock_service

        # Should work at /health
        response = client.get("/health")
        assert response.status_code == 200

        # Should NOT work at /api/v1/health
        response = client.get("/api/v1/health")
        assert response.status_code == 404

    def test_ready_at_root_level(self, client: TestClient, mock_preflight_service: MagicMock):
        """/ready is accessible at root, not under /api/v1."""
        mock_service = MagicMock()
        mock_service.run_all_checks.return_value = PreflightResult(
            checks=[],
            blocking_failures=0,
            warnings=0,
        )
        mock_service.check_database_schema_current.return_value = PreflightCheck(
            code="DB_SCHEMA_CURRENT",
            service="database",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="OK",
            remediation="",
        )
        mock_service.check_picoclaw_snapshot_exists.return_value = PreflightCheck(
            code="PICOCLAW_SNAPSHOT",
            service="daytona",
            severity=CheckSeverity.BLOCKING,
            status=CheckStatus.PASS,
            message="OK",
            remediation="",
        )
        mock_preflight_service.return_value = mock_service

        # Should work at /ready
        response = client.get("/ready")
        assert response.status_code == 200

        # Should NOT work at /api/v1/ready
        response = client.get("/api/v1/ready")
        assert response.status_code == 404

    def test_api_v1_routes_not_affected(self, client: TestClient):
        """Existing /api/v1 routes continue to work alongside OSS endpoints."""
        # The /api/v1/ root should still exist
        response = client.get("/api/v1/")
        # This should work (API root endpoint)
        assert response.status_code == 200


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_metrics_endpoint_exists(self, client: TestClient):
        """Metrics endpoint is exposed at root level."""
        response = client.get("/metrics")
        # Metrics endpoint should exist and return Prometheus format
        assert response.status_code == 200
        # Prometheus metrics are text/plain
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_includes_default_fastapi_metrics(self, client: TestClient):
        """Metrics include default FastAPI/HTTP metrics from instrumentator."""
        # Make a few requests to generate metrics
        client.get("/health")
        client.get("/ready")

        response = client.get("/metrics")
        content = response.text

        # Default instrumentator metrics include http_request_duration_seconds
        assert "http_request" in content.lower() or "request" in content.lower()

    def test_metrics_endpoint_does_not_require_auth(self, client: TestClient):
        """Metrics endpoint is accessible without authentication."""
        response = client.get("/metrics")
        # Should not return 401 or 403
        assert response.status_code != 401
        assert response.status_code != 403

    def test_metrics_at_root_level(self, client: TestClient):
        """/metrics is accessible at root, not under /api/v1."""
        # Should work at /metrics
        response = client.get("/metrics")
        assert response.status_code == 200

        # Should NOT work at /api/v1/metrics
        response = client.get("/api/v1/metrics")
        assert response.status_code == 404
