"""Regression tests for deprecated bridge helpers in RunService.

These tests verify that backwards-compatibility methods remain functional
after the Picoclaw to Zeroclaw migration.

Gap closed: VERIFICATION Gap 1 - RunService._is_recoverable_bridge_error
referenced deleted BridgeErrorType.
"""

import pytest

from src.services.run_service import RunService
from src.services.zeroclaw_gateway_service import GatewayError, GatewayErrorType


class TestDeprecatedBridgeRecoverability:
    """Tests for deprecated _is_recoverable_bridge_error method."""

    @pytest.fixture
    def run_service(self):
        """Create a RunService instance for testing."""
        return RunService()

    def test_is_recoverable_bridge_error_none_returns_false(self, run_service):
        """Test that None error returns False (fail-closed behavior)."""
        result = run_service._is_recoverable_bridge_error(None)
        assert result is False

    @pytest.mark.parametrize(
        "error_type",
        [
            GatewayErrorType.HEALTH_CHECK_FAILED,
            GatewayErrorType.TIMEOUT,
            GatewayErrorType.TRANSPORT_ERROR,
        ],
    )
    def test_is_recoverable_bridge_error_recoverable_types_return_true(
        self, run_service, error_type
    ):
        """Test that recoverable error types return True."""
        error = GatewayError(
            error_type=error_type,
            message="Test error message",
            remediation="Test remediation",
        )
        result = run_service._is_recoverable_bridge_error(error)
        assert result is True, f"Expected True for {error_type.value}"

    @pytest.mark.parametrize(
        "error_type",
        [
            GatewayErrorType.AUTH_FAILED,
            GatewayErrorType.UPSTREAM_ERROR,
            GatewayErrorType.MALFORMED_RESPONSE,
        ],
    )
    def test_is_recoverable_bridge_error_non_recoverable_types_return_false(
        self, run_service, error_type
    ):
        """Test that non-recoverable error types return False."""
        error = GatewayError(
            error_type=error_type,
            message="Test error message",
            remediation="Test remediation",
        )
        result = run_service._is_recoverable_bridge_error(error)
        assert result is False, f"Expected False for {error_type.value}"

    def test_is_recoverable_bridge_error_consistency_with_gateway_method(
        self, run_service
    ):
        """Test that deprecated method returns same results as new method."""
        # Test with recoverable type
        recoverable_error = GatewayError(
            error_type=GatewayErrorType.TIMEOUT,
            message="Timeout error",
            remediation="Retry",
        )
        bridge_result = run_service._is_recoverable_bridge_error(recoverable_error)
        gateway_result = run_service._is_recoverable_gateway_error(recoverable_error)
        assert bridge_result == gateway_result

        # Test with non-recoverable type
        non_recoverable_error = GatewayError(
            error_type=GatewayErrorType.AUTH_FAILED,
            message="Auth failed",
            remediation="Check token",
        )
        bridge_result = run_service._is_recoverable_bridge_error(non_recoverable_error)
        gateway_result = run_service._is_recoverable_gateway_error(
            non_recoverable_error
        )
        assert bridge_result == gateway_result

        # Test with None
        bridge_result = run_service._is_recoverable_bridge_error(None)
        gateway_result = run_service._is_recoverable_gateway_error(None)
        assert bridge_result == gateway_result
