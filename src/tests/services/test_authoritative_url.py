"""Regression tests for authoritative gateway URL enforcement in RunService.

These tests verify that RunService never fabricates sandbox gateway URLs;
it uses only authoritative gateway_url values resolved during provisioning.

Gap closed: VERIFICATION Gap - Authoritative URL enforcement
Tests the fail-closed behavior where no synthetic URL construction is permitted.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from src.services.run_service import RunService, RunRoutingResult


@dataclass
class MockSandbox:
    """Mock sandbox object for testing URL resolution."""

    id: str
    gateway_url: Optional[str] = None


@dataclass
class MockRoutingResult:
    """Mock routing result containing sandbox info."""

    sandbox: Optional[MockSandbox] = None
    success: bool = True
    message: Optional[str] = None


@dataclass
class MockLifecycleTarget:
    """Mock lifecycle target with routing result."""

    routing_result: Optional[MockRoutingResult] = None
    agent_pack_id: Optional[str] = None
    principal: Optional[object] = None


class TestAuthoritativeUrlEnforcement:
    """Tests for fail-closed authoritative URL resolution."""

    @pytest.fixture
    def run_service(self):
        """Create a RunService instance for testing."""
        return RunService()

    def test_returns_sandbox_url_when_present(self, run_service):
        """Test 1: When sandbox_url is set on RunRoutingResult, return it."""
        routing = RunRoutingResult(
            success=True,
            sandbox_url="https://sandbox-gateway.example.com/webhook",
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result == "https://sandbox-gateway.example.com/webhook"

    def test_returns_lifecycle_target_url_when_sandbox_url_missing(self, run_service):
        """Test 2: When sandbox_url is missing but lifecycle target has gateway_url, return that."""
        mock_sandbox = MockSandbox(
            id="sandbox-123",
            gateway_url="https://lifecycle-gateway.example.com/webhook",
        )
        mock_routing_result = MockRoutingResult(sandbox=mock_sandbox, success=True)
        mock_lifecycle_target = MockLifecycleTarget(routing_result=mock_routing_result)

        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,  # No direct sandbox_url
            lifecycle_target=mock_lifecycle_target,
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result == "https://lifecycle-gateway.example.com/webhook"

    def test_returns_none_when_no_url_available(self, run_service):
        """Test 3: When neither sandbox_url nor lifecycle target URL is present, return None."""
        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,
            lifecycle_target=None,  # No lifecycle target
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result is None

    def test_returns_none_when_lifecycle_target_has_no_routing_result(
        self, run_service
    ):
        """Test: When lifecycle target exists but has no routing result, return None."""
        mock_lifecycle_target = MockLifecycleTarget(routing_result=None)

        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,
            lifecycle_target=mock_lifecycle_target,
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result is None

    def test_returns_none_when_routing_result_has_no_sandbox(self, run_service):
        """Test: When routing result exists but has no sandbox, return None."""
        mock_routing_result = MockRoutingResult(sandbox=None, success=True)
        mock_lifecycle_target = MockLifecycleTarget(routing_result=mock_routing_result)

        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,
            lifecycle_target=mock_lifecycle_target,
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result is None

    def test_returns_none_when_sandbox_has_no_gateway_url(self, run_service):
        """Test: When sandbox exists but has no gateway_url attribute, return None."""
        mock_sandbox = MockSandbox(
            id="sandbox-123",
            gateway_url=None,  # No gateway URL
        )
        mock_routing_result = MockRoutingResult(sandbox=mock_sandbox, success=True)
        mock_lifecycle_target = MockLifecycleTarget(routing_result=mock_routing_result)

        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,
            lifecycle_target=mock_lifecycle_target,
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        assert result is None

    def test_prefers_sandbox_url_over_lifecycle_target(self, run_service):
        """Test: When both sandbox_url and lifecycle target URL exist, prefer sandbox_url."""
        mock_sandbox = MockSandbox(
            id="sandbox-123",
            gateway_url="https://lifecycle-gateway.example.com/webhook",
        )
        mock_routing_result = MockRoutingResult(sandbox=mock_sandbox, success=True)
        mock_lifecycle_target = MockLifecycleTarget(routing_result=mock_routing_result)

        routing = RunRoutingResult(
            success=True,
            sandbox_url="https://direct-sandbox-url.example.com/webhook",  # Direct URL takes precedence
            lifecycle_target=mock_lifecycle_target,
            workspace_id="test-workspace-id",
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        # Should prefer the direct sandbox_url, not the lifecycle target URL
        assert result == "https://direct-sandbox-url.example.com/webhook"

    def test_no_synthetic_url_construction_attempted(self, run_service):
        """Test: Verify that no synthetic URL construction is attempted.

        This is the core fail-closed invariant: we never construct URLs from
        workspace IDs or other identifiers - only authoritative URLs are used.
        """
        routing = RunRoutingResult(
            success=True,
            sandbox_url=None,
            lifecycle_target=None,
            workspace_id="test-workspace-123",  # Workspace ID present but not used for URL construction
        )

        result = run_service._get_authoritative_sandbox_url(routing)

        # Should return None, not construct a URL like:
        # - "https://test-workspace-123.sandbox.example.com"
        # - "http://localhost:8080/workspace/test-workspace-123"
        # - etc.
        assert result is None

        # Verify no workspace-ID-based URL was constructed
        assert "test-workspace-123" not in (result or "")
        assert result is None or not result.startswith("http")
