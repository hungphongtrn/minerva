"""Regression tests for bounded recovery semantics in RunService.

These tests verify that RunService implements proper bounded recovery:
- Max 3 attempts for recoverable errors
- Fail-fast for non-recoverable errors
- Recovery exhaustion returns TRANSPORT_ERROR

Gap closed: VERIFICATION Gap - Bounded recovery around ZeroclawGatewayService
Tests the recovery loop and error classification invariants.
"""

import pytest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.run_service import RunService, RunRoutingResult
from src.services.zeroclaw_gateway_service import (
    GatewayError,
    GatewayErrorType,
    GatewayResult,
    GatewayTokenBundle,
)


@dataclass
class MockLifecycleTarget:
    """Mock lifecycle target for testing."""

    agent_pack_id: Optional[str] = None
    principal: Optional[object] = None


class TestBoundedRecovery:
    """Tests for bounded recovery semantics (max 3 attempts, reprovision on recoverable errors)."""

    @pytest.fixture
    def run_service(self):
        """Create a RunService instance for testing."""
        return RunService()

    @pytest.fixture
    def mock_routing(self):
        """Create a mock routing result for testing."""
        return RunRoutingResult(
            success=True,
            sandbox_url="https://sandbox.example.com/webhook",
            workspace_id=str(uuid4()),
            sandbox_id=str(uuid4()),
            lifecycle_target=MockLifecycleTarget(agent_pack_id="test-pack"),
            run_id=str(uuid4()),
        )

    @pytest.fixture
    def mock_token_bundle(self):
        """Create a mock token bundle for testing."""
        return GatewayTokenBundle(
            current="test-token-current",
            previous="test-token-previous",
        )

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session for testing."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_recoverable_error_triggers_reprovision_and_retry(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test 1: Recoverable errors trigger reprovision and retry up to 3 attempts.

        Recoverable errors: HEALTH_CHECK_FAILED, TIMEOUT, TRANSPORT_ERROR
        """
        # Arrange: Mock gateway service to fail with recoverable error twice, then succeed
        mock_gateway = MagicMock()
        mock_gateway.execute = AsyncMock(
            side_effect=[
                GatewayResult(
                    success=False,
                    error=GatewayError(
                        error_type=GatewayErrorType.TIMEOUT,
                        message="Connection timeout",
                    ),
                ),
                GatewayResult(
                    success=False,
                    error=GatewayError(
                        error_type=GatewayErrorType.TIMEOUT,
                        message="Connection timeout again",
                    ),
                ),
                GatewayResult(
                    success=True,
                    output={"message": "Success!"},
                ),
            ]
        )

        # Mock the factory to return our mock
        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

        # Mock recovery to return a fresh routing (simulating reprovision)
        recovered_routing = RunRoutingResult(
            success=True,
            sandbox_url="https://recovered-sandbox.example.com/webhook",
            workspace_id=mock_routing.workspace_id,
            sandbox_id=str(uuid4()),
            lifecycle_target=MockLifecycleTarget(agent_pack_id="test-pack"),
            run_id=str(uuid4()),
        )
        run_service._recover_routing_target = AsyncMock(return_value=recovered_routing)

        # Mock token resolution
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert result.success is True
        assert result.output == {"message": "Success!"}
        # Should have called gateway.execute 3 times (2 failures + 1 success)
        assert mock_gateway.execute.call_count == 3
        # Should have called recovery twice (after first and second failure)
        assert run_service._recover_routing_target.call_count == 2

    @pytest.mark.asyncio
    async def test_all_recoverable_error_types_trigger_retry(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test that all recoverable error types trigger retry behavior."""
        recoverable_types = [
            GatewayErrorType.HEALTH_CHECK_FAILED,
            GatewayErrorType.TIMEOUT,
            GatewayErrorType.TRANSPORT_ERROR,
        ]

        for error_type in recoverable_types:
            # Arrange
            mock_gateway = MagicMock()
            mock_gateway.execute = AsyncMock(
                return_value=GatewayResult(
                    success=False,
                    error=GatewayError(
                        error_type=error_type,
                        message=f"Test {error_type.value}",
                    ),
                )
            )

            run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

            recovered_routing = RunRoutingResult(
                success=True,
                sandbox_url="https://recovered.example.com/webhook",
                workspace_id=mock_routing.workspace_id,
                sandbox_id=str(uuid4()),
                lifecycle_target=MockLifecycleTarget(agent_pack_id="test-pack"),
                run_id=str(uuid4()),
            )
            run_service._recover_routing_target = AsyncMock(
                return_value=recovered_routing
            )
            run_service._resolve_gateway_tokens = MagicMock(
                return_value=mock_token_bundle
            )

            # Act
            result = await run_service._execute_via_gateway(
                routing=mock_routing,
                message="Hello",
                is_guest=False,
                session=mock_session,
            )

            # Assert: Should retry up to 3 times with recovery between
            assert result.success is False  # All attempts fail
            assert mock_gateway.execute.call_count == 3  # Max attempts
            assert (
                run_service._recover_routing_target.call_count == 2
            )  # Recovery between attempts

            # Reset for next iteration
            run_service._recover_routing_target.reset_mock()

    @pytest.mark.asyncio
    async def test_non_recoverable_error_fails_fast_no_retry(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test 2: Non-recoverable errors fail fast with single attempt (no reprovision loop).

        Non-recoverable errors: AUTH_FAILED, UPSTREAM_ERROR, MALFORMED_RESPONSE
        """
        non_recoverable_types = [
            GatewayErrorType.AUTH_FAILED,
            GatewayErrorType.UPSTREAM_ERROR,
            GatewayErrorType.MALFORMED_RESPONSE,
        ]

        for error_type in non_recoverable_types:
            # Arrange
            mock_gateway = MagicMock()
            mock_gateway.execute = AsyncMock(
                return_value=GatewayResult(
                    success=False,
                    error=GatewayError(
                        error_type=error_type,
                        message=f"Test {error_type.value}",
                    ),
                )
            )

            run_service._create_gateway_service = MagicMock(return_value=mock_gateway)
            run_service._recover_routing_target = AsyncMock()  # Should NOT be called
            run_service._resolve_gateway_tokens = MagicMock(
                return_value=mock_token_bundle
            )

            # Act
            result = await run_service._execute_via_gateway(
                routing=mock_routing,
                message="Hello",
                is_guest=False,
                session=mock_session,
            )

            # Assert
            assert result.success is False
            assert result.error.error_type == error_type
            # Should have called gateway.execute only once (fail fast)
            assert mock_gateway.execute.call_count == 1
            # Should NOT have attempted recovery
            run_service._recover_routing_target.assert_not_called()

            # Reset for next iteration
            run_service._recover_routing_target.reset_mock()

    @pytest.mark.asyncio
    async def test_recovery_exhaustion_returns_transport_error(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test 3: On recovery exhaustion, returned GatewayResult has TRANSPORT_ERROR."""
        # Arrange: Always fail with recoverable error
        mock_gateway = MagicMock()
        mock_gateway.execute = AsyncMock(
            return_value=GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TIMEOUT,
                    message="Persistent timeout",
                ),
            )
        )

        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

        # Recovery always succeeds but new sandbox also fails
        recovered_routing = RunRoutingResult(
            success=True,
            sandbox_url="https://recovered-sandbox.example.com/webhook",
            workspace_id=mock_routing.workspace_id,
            sandbox_id=str(uuid4()),
            lifecycle_target=MockLifecycleTarget(agent_pack_id="test-pack"),
            run_id=str(uuid4()),
        )
        run_service._recover_routing_target = AsyncMock(return_value=recovered_routing)
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert result.success is False
        assert result.error.error_type == GatewayErrorType.TRANSPORT_ERROR
        assert "3 recovery attempts" in result.error.message
        assert "Persistent timeout" in result.error.message

    @pytest.mark.asyncio
    async def test_max_three_attempts_enforced(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test that exactly 3 attempts are made before giving up."""
        # Arrange: Track calls
        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TRANSPORT_ERROR,
                    message=f"Attempt {call_count} failed",
                ),
            )

        mock_gateway = MagicMock()
        mock_gateway.execute = mock_execute

        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

        recovered_routing = RunRoutingResult(
            success=True,
            sandbox_url=f"https://recovered-sandbox.example.com/webhook",
            workspace_id=mock_routing.workspace_id,
            sandbox_id=str(uuid4()),
            lifecycle_target=MockLifecycleTarget(agent_pack_id="test-pack"),
            run_id=str(uuid4()),
        )
        run_service._recover_routing_target = AsyncMock(return_value=recovered_routing)
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert call_count == 3
        assert result.success is False

    @pytest.mark.asyncio
    async def test_recovery_failure_returns_transport_error(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test that recovery failure during reprovisioning returns TRANSPORT_ERROR."""
        # Arrange: First attempt fails
        mock_gateway = MagicMock()
        mock_gateway.execute = AsyncMock(
            return_value=GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TIMEOUT,
                    message="Initial timeout",
                ),
            )
        )

        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

        # Recovery fails
        failed_recovery = RunRoutingResult(
            success=False,
            error="Recovery reprovisioning failed",
            workspace_id=mock_routing.workspace_id,
            run_id=str(uuid4()),
        )
        run_service._recover_routing_target = AsyncMock(return_value=failed_recovery)
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert result.success is False
        assert result.error.error_type == GatewayErrorType.TRANSPORT_ERROR
        assert "Recovery reprovisioning failed" in result.error.message

    @pytest.mark.asyncio
    async def test_recovery_exception_returns_transport_error(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test that recovery exception returns TRANSPORT_ERROR with exception info."""
        # Arrange: First attempt fails
        mock_gateway = MagicMock()
        mock_gateway.execute = AsyncMock(
            return_value=GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TIMEOUT,
                    message="Initial timeout",
                ),
            )
        )

        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)

        # Recovery throws exception
        run_service._recover_routing_target = AsyncMock(
            side_effect=Exception("Provider connection refused")
        )
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert result.success is False
        assert result.error.error_type == GatewayErrorType.TRANSPORT_ERROR
        assert "Provider connection refused" in result.error.message

    @pytest.mark.asyncio
    async def test_first_success_returns_immediately(
        self, run_service, mock_routing, mock_token_bundle, mock_session
    ):
        """Test that immediate success returns on first attempt without recovery."""
        # Arrange
        mock_gateway = MagicMock()
        mock_gateway.execute = AsyncMock(
            return_value=GatewayResult(
                success=True,
                output={"message": "First try success!"},
            )
        )

        run_service._create_gateway_service = MagicMock(return_value=mock_gateway)
        run_service._recover_routing_target = AsyncMock()  # Should not be called
        run_service._resolve_gateway_tokens = MagicMock(return_value=mock_token_bundle)

        # Act
        result = await run_service._execute_via_gateway(
            routing=mock_routing,
            message="Hello",
            is_guest=False,
            session=mock_session,
        )

        # Assert
        assert result.success is True
        assert result.output == {"message": "First try success!"}
        assert mock_gateway.execute.call_count == 1
        run_service._recover_routing_target.assert_not_called()
