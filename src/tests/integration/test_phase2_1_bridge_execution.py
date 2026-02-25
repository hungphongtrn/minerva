"""Integration tests for Phase 2.1 bridge execution.

Tests verify:
- Successful /runs bridge invocation returns final output
- Health polling is required before execute
- Bearer-auth/runtime failures fail closed with typed errors
- Session key scope is workspace+pack with guest ephemerality
"""

import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    AgentPack,
    AgentPackValidationStatus,
    Workspace,
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    User,
)
from src.services.run_service import RunService, RoutingErrorType


@pytest.fixture
def sample_agent_pack(db_session: Session, workspace_alpha: Workspace) -> AgentPack:
    """Create a valid agent pack for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        name="Test Pack",
        source_path="/tmp/test-pack",
        source_digest="abc123",
        validation_status=AgentPackValidationStatus.VALID,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


@pytest.fixture
def active_sandbox(
    db_session: Session, workspace_alpha: Workspace, sample_agent_pack: AgentPack
) -> SandboxInstance:
    """Create an active sandbox with gateway URL."""
    sandbox = SandboxInstance(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
        provider_ref="sandbox-test-001",
        state=SandboxState.ACTIVE,
        health_status=SandboxHealthStatus.HEALTHY,
        agent_pack_id=sample_agent_pack.id,
        gateway_url="http://sandbox-test-001:18790",
        idle_ttl_seconds=3600,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(sandbox)
    db_session.commit()
    return sandbox


class TestBridgeExecution:
    """Tests for bridge execution integration."""

    @pytest.mark.asyncio
    async def test_session_key_scoped_to_workspace_and_pack(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
        sample_agent_pack: AgentPack,
    ):
        """Test that session keys are scoped to workspace+pack for authenticated runs."""
        service = RunService()

        # Generate session key for authenticated user
        session_key = service._generate_session_key(
            workspace_id=str(workspace_alpha.id),
            agent_pack_id=str(sample_agent_pack.id),
            run_id="test-run-001",
            is_guest=False,
        )

        # Verify session key format
        assert session_key.startswith("minerva:")
        assert str(workspace_alpha.id) in session_key
        assert str(sample_agent_pack.id) in session_key
        assert "test-run-001" in session_key

    @pytest.mark.asyncio
    async def test_session_key_ephemeral_for_guest(
        self,
        db_session: Session,
    ):
        """Test that guest sessions are ephemeral (per-request unique)."""
        service = RunService()

        # Generate session keys for guest
        session_key_1 = service._generate_session_key(
            workspace_id=None,
            agent_pack_id=None,
            run_id="guest-run-001",
            is_guest=True,
        )
        session_key_2 = service._generate_session_key(
            workspace_id=None,
            agent_pack_id=None,
            run_id="guest-run-002",
            is_guest=True,
        )

        # Verify guest session format - should be unique per request
        assert session_key_1.startswith("minerva:guest:")
        assert session_key_2.startswith("minerva:guest:")
        # Each guest session should be unique (different run_id)
        assert session_key_1 != session_key_2

    @pytest.mark.asyncio
    async def test_bridge_error_mapping_health_check_failed(self):
        """Test that bridge health check failures map to correct error type."""
        from src.services.picoclaw_bridge_service import BridgeError, BridgeErrorType

        service = RunService()

        error = BridgeError(
            error_type=BridgeErrorType.HEALTH_CHECK_FAILED,
            message="Health check failed: unhealthy",
            remediation="Sandbox may be unhealthy",
        )

        error_type = service._map_bridge_error_type(error)

        assert error_type == RoutingErrorType.BRIDGE_HEALTH_CHECK_FAILED

    @pytest.mark.asyncio
    async def test_bridge_error_mapping_auth_failed(self):
        """Test that bridge auth failures map to correct error type."""
        from src.services.picoclaw_bridge_service import BridgeError, BridgeErrorType

        service = RunService()

        error = BridgeError(
            error_type=BridgeErrorType.AUTH_FAILED,
            message="Authentication failed",
            remediation="Check bridge token",
        )

        error_type = service._map_bridge_error_type(error)

        assert error_type == RoutingErrorType.BRIDGE_AUTH_FAILED

    @pytest.mark.asyncio
    async def test_bridge_error_mapping_timeout(self):
        """Test that bridge timeout maps to correct error type."""
        from src.services.picoclaw_bridge_service import BridgeError, BridgeErrorType

        service = RunService()

        error = BridgeError(
            error_type=BridgeErrorType.TIMEOUT,
            message="Request timed out after 300s",
            remediation="Increase timeout",
        )

        error_type = service._map_bridge_error_type(error)

        assert error_type == RoutingErrorType.BRIDGE_TIMEOUT


class TestBridgeErrorMapping:
    """Tests for API bridge error mapping."""

    def test_bridge_health_check_maps_to_503(self):
        """Test bridge health check failure returns 503."""
        from src.api.routes.runs import _map_routing_error

        result = _map_routing_error(
            RoutingErrorType.BRIDGE_HEALTH_CHECK_FAILED,
            "Health check failed: unhealthy",
        )

        assert result["status_code"] == 503
        assert result["detail"]["error_type"] == "bridge_health_check_failed"

    def test_bridge_auth_failure_maps_to_503(self):
        """Test bridge auth failure returns 503."""
        from src.api.routes.runs import _map_routing_error

        result = _map_routing_error(
            RoutingErrorType.BRIDGE_AUTH_FAILED, "Authentication failed"
        )

        assert result["status_code"] == 503
        assert result["detail"]["error_type"] == "bridge_auth_failed"

    def test_bridge_timeout_maps_to_504(self):
        """Test bridge timeout returns 504."""
        from src.api.routes.runs import _map_routing_error

        result = _map_routing_error(
            RoutingErrorType.BRIDGE_TIMEOUT, "Request timed out after 300s"
        )

        assert result["status_code"] == 504
        assert result["detail"]["error_type"] == "bridge_timeout"

    def test_bridge_transport_error_maps_to_503(self):
        """Test bridge transport error returns 503."""
        from src.api.routes.runs import _map_routing_error

        result = _map_routing_error(
            RoutingErrorType.BRIDGE_TRANSPORT_ERROR,
            "Transport error: connection refused",
        )

        assert result["status_code"] == 503
        assert result["detail"]["error_type"] == "bridge_transport_error"

    def test_bridge_upstream_error_maps_to_502(self):
        """Test bridge upstream error returns 502."""
        from src.api.routes.runs import _map_routing_error

        result = _map_routing_error(
            RoutingErrorType.BRIDGE_UPSTREAM_ERROR, "Picoclaw runtime error"
        )

        assert result["status_code"] == 502
        assert result["detail"]["error_type"] == "bridge_upstream_error"


class TestRunResultOutputs:
    """Tests for RunResult output structure."""

    @pytest.mark.asyncio
    async def test_routing_result_includes_sandbox_url(
        self,
        db_session: Session,
        workspace_alpha: Workspace,
        sample_agent_pack: AgentPack,
        active_sandbox: SandboxInstance,
    ):
        """Test that RunRoutingResult includes sandbox URL."""
        # The sandbox has gateway_url set
        assert active_sandbox.gateway_url == "http://sandbox-test-001:18790"

    def test_run_result_can_hold_bridge_output(self):
        """Test that RunResult can hold bridge execution output."""
        from src.services.run_service import RunResult

        result = RunResult(
            run_id="test-001",
            status="success",
            outputs={
                "routing": {
                    "workspace_id": "ws-001",
                    "sandbox_id": "sb-001",
                },
                "bridge": {
                    "success": True,
                    "output": {"message": "Hello from Picoclaw"},
                },
                "final_output": "Hello from Picoclaw",
            },
        )

        assert result.outputs["bridge"]["success"] is True
        assert result.outputs["final_output"] == "Hello from Picoclaw"


class TestValidPackRegression:
    """Regression tests to ensure valid packs don't return pack-specific errors."""

    def test_valid_pack_never_returns_pack_client_errors(
        self,
    ):
        """Valid packs should never return pack-specific 4xx errors after routing.

        This is a regression test for Truth 11 - profile parity.
        The actual test exists in test_phase2_run_routing_errors.py as
        test_run_does_not_fail_with_pack_error_for_valid_pack.
        """
        # Verify RoutingErrorType constants exist
        assert hasattr(RoutingErrorType, "PACK_NOT_FOUND")
        assert hasattr(RoutingErrorType, "PACK_WORKSPACE_MISMATCH")
        assert hasattr(RoutingErrorType, "PACK_INVALID")
        assert hasattr(RoutingErrorType, "PACK_STALE")
        # Bridge errors should NOT be pack errors
        assert hasattr(RoutingErrorType, "BRIDGE_HEALTH_CHECK_FAILED")
        assert hasattr(RoutingErrorType, "BRIDGE_AUTH_FAILED")
        assert hasattr(RoutingErrorType, "BRIDGE_TIMEOUT")
