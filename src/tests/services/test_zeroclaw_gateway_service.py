"""Service-level tests for Zeroclaw gateway service.

These tests verify:
1. Health is polled before execution
2. Bearer token is attached to requests (when spec requires bearer)
3. Health/auth failures short-circuit execute path
4. Timeout and retry behavior is bounded
5. Error typing is stable for API mapping
6. Spec-driven configuration is respected

Uses mocked HTTP transport - does not require live sandbox runtime.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.integrations.zeroclaw.spec import (
    ZeroclawSpec,
    GatewaySpec,
    AuthSpec,
    RuntimeSpec,
    ExamplesSpec,
)
from src.services.zeroclaw_gateway_service import (
    ZeroclawGatewayService,
    GatewayErrorType,
    GatewayResult,
    GatewayTokenBundle,
    execute_via_gateway,
)


# Constants for tests
SANDBOX_URL = "http://sandbox:18790"
MESSAGE = "Hello, agent!"
SESSION_KEY = "minerva:workspace-123:pack-456:run-789"
WORKSPACE_ID = "workspace-123"
AGENT_PACK_ID = "pack-456"
RUN_ID = "run-789"
TEST_TOKEN_BUNDLE = GatewayTokenBundle(current="test-token-current")


def create_test_spec(auth_mode: str = "bearer") -> ZeroclawSpec:
    """Create a test ZeroclawSpec with specified auth mode."""
    return ZeroclawSpec(
        version="1.0.0",
        gateway=GatewaySpec(
            port=18790,
            health_path="/health",
            execute_path="/execute",
            stream_mode="sse",
        ),
        auth=AuthSpec(mode=auth_mode),  # type: ignore[arg-type]
        runtime=RuntimeSpec(
            config_path="/workspace/.zeroclaw/config.json",
            start_command="zeroclaw-gateway --config /workspace/.zeroclaw/config.json",
        ),
        examples=ExamplesSpec(
            execute_request={
                "message": "Hello, Zeroclaw!",
                "context": {"session_id": "session-123", "sender_id": "user-456"},
            },
            execute_response={
                "success": True,
                "output": {
                    "message": "Response from Zeroclaw",
                    "timestamp": "2026-03-05T00:00:00Z",
                },
            },
        ),
    )


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_check_health_returns_healthy_on_200(self):
        """Health check returns healthy status on 200 response."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "uptime": 100}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is True
            assert status.status == "ok"

    @pytest.mark.asyncio
    async def test_check_health_returns_unhealthy_on_500(self):
        """Health check returns unhealthy status on 500 response."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "internal error"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is False
            assert status.status == "unhealthy"

    @pytest.mark.asyncio
    async def test_check_health_returns_unauthorized_on_401(self):
        """Health check returns unhealthy with auth failure on 401."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 401

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is False
            assert status.status == "unauthorized"

    @pytest.mark.asyncio
    async def test_check_health_returns_timeout_on_timeout(self):
        """Health check returns unhealthy on timeout."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is False
            assert status.status == "timeout"

    @pytest.mark.asyncio
    async def test_check_health_uses_spec_health_path(self):
        """Health check uses health_path from spec."""
        spec = create_test_spec()
        # Modify health path
        spec.gateway.health_path = "/custom/health"
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await service.check_health(SANDBOX_URL)

            # Verify correct URL was called
            call_args = mock_get.call_args
            assert "/custom/health" in call_args.args[0]


class TestHealthPolling:
    """Tests for health polling with retries."""

    @pytest.mark.asyncio
    async def test_poll_health_succeeds_on_first_attempt(self):
        """Poll returns healthy on first successful health check."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=3, health_backoff=0.01
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await service.poll_health(SANDBOX_URL)

            assert status.healthy is True
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_poll_health_retries_on_failure(self):
        """Poll retries on health check failures."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=3, health_backoff=0.01
        )

        # First two calls fail, third succeeds
        mock_response_fail = AsyncMock(spec=httpx.Response)
        mock_response_fail.status_code = 500

        mock_response_success = AsyncMock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                mock_response_fail,
                mock_response_fail,
                mock_response_success,
            ]

            status = await service.poll_health(SANDBOX_URL)

            assert status.healthy is True
            assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_health_fails_closed_after_retries_exhausted(self):
        """Poll returns unhealthy after exhausting retries."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=2, health_backoff=0.01
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await service.poll_health(SANDBOX_URL)

            assert status.healthy is False
            # Initial + 2 retries = 3 calls
            assert mock_get.call_count == 3


class TestAuthentication:
    """Tests for bearer token authentication."""

    @pytest.mark.asyncio
    async def test_bearer_token_attached_when_spec_requires_auth(self):
        """Bearer token is attached when spec requires bearer auth."""
        spec = create_test_spec(auth_mode="bearer")
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await service.check_health(SANDBOX_URL, token_bundle=TEST_TOKEN_BUNDLE)

            # Verify Authorization header was sent
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_no_bearer_token_when_spec_has_no_auth(self):
        """No bearer token when spec has no auth."""
        spec = create_test_spec(auth_mode="none")
        service = ZeroclawGatewayService(spec=spec)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await service.check_health(SANDBOX_URL, token_bundle=TEST_TOKEN_BUNDLE)

            # Verify Authorization header was NOT sent (auth not required)
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_bearer_token_attached_to_execute_request(self):
        """Bearer token is attached to execute requests with token_bundle."""
        spec = create_test_spec(auth_mode="bearer")
        service = ZeroclawGatewayService(spec=spec)

        # Mock health check to pass
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        mock_execute_response = AsyncMock(spec=httpx.Response)
        mock_execute_response.status_code = 200
        mock_execute_response.json.return_value = {"output": "test"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.return_value = mock_execute_response

            await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            # Verify Authorization header was sent
            call_args = mock_post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_fail_closed_when_auth_required_but_no_token(self):
        """Execute fails closed when bearer auth required but no token provided."""
        spec = create_test_spec(auth_mode="bearer")
        service = ZeroclawGatewayService(spec=spec)

        result = await service.execute(
            sandbox_url=SANDBOX_URL,
            message=MESSAGE,
            session_key=SESSION_KEY,
            token_bundle=None,  # No token bundle
        )

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == GatewayErrorType.AUTH_FAILED


class TestFailClosed:
    """Tests for fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_execute_blocked_when_health_fails(self):
        """Execute is blocked when health check fails."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=1, health_backoff=0.01
        )

        # Health check always fails
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.success is False
            assert result.error is not None
            assert result.error.error_type == GatewayErrorType.HEALTH_CHECK_FAILED

    @pytest.mark.asyncio
    async def test_execute_blocked_on_auth_failure(self):
        """Execute is blocked when authentication fails."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=1, health_backoff=0.01
        )

        # Health check returns 401
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 401

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_health_response

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.success is False
            assert result.error is not None
            assert result.error.error_type == GatewayErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_no_execute_attempted_when_health_fails(self):
        """Verify execute endpoint is never called when health fails."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=1, health_backoff=0.01
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_response
            mock_post.return_value = mock_response  # Should never be called

            await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            # Execute should never be called
            assert mock_post.call_count == 0


class TestTimeout:
    """Tests for timeout behavior."""

    @pytest.mark.asyncio
    async def test_execute_timeout_returns_typed_error(self):
        """Execute returns typed timeout error on timeout."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_timeout=5, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.success is False
            assert result.error is not None
            assert result.error.error_type == GatewayErrorType.TIMEOUT
            assert "timed out" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_health_timeout_returns_typed_error(self):
        """Health check returns typed error on timeout."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_timeout=5)

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Health check timeout")

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is False
            assert status.status == "timeout"


class TestRetry:
    """Tests for retry behavior."""

    @pytest.mark.asyncio
    async def test_execute_retries_on_transient_failure(self):
        """Execute retries on transient failures when retries > 0."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_retries=2, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # First two execute calls fail with 500, third succeeds
        mock_fail_response = AsyncMock(spec=httpx.Response)
        mock_fail_response.status_code = 500
        mock_fail_response.json.return_value = {"error": "internal error"}

        mock_success_response = AsyncMock(spec=httpx.Response)
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {"output": "success"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.side_effect = [
                mock_fail_response,
                mock_fail_response,
                mock_success_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.success is True
            assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_no_retry_on_client_error(self):
        """Execute does not retry on 4xx errors."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_retries=2, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Execute returns 400 (client error)
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "bad request"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.return_value = mock_response

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            # Should not retry on 4xx
            assert mock_post.call_count == 1
            assert result.success is False
            assert result.error.status_code == 400


class TestErrorTyping:
    """Tests for stable error typing."""

    @pytest.mark.asyncio
    async def test_transport_error_returns_typed_error(self):
        """Transport errors return TRANSPORT_ERROR type."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_timeout=5, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.side_effect = httpx.RequestError("Connection refused")

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.error.error_type == GatewayErrorType.TRANSPORT_ERROR

    @pytest.mark.asyncio
    async def test_malformed_response_returns_typed_error(self):
        """Malformed JSON responses return MALFORMED_RESPONSE type."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_retries=0, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Execute returns 200 but invalid JSON
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.return_value = mock_response

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.error.error_type == GatewayErrorType.MALFORMED_RESPONSE

    @pytest.mark.asyncio
    async def test_error_includes_remediation(self):
        """Errors include remediation guidance."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec, health_retries=0, execute_timeout=5, health_backoff=0.01
        )

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.side_effect = httpx.TimeoutException("timeout")

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            assert result.error.remediation is not None
            assert len(result.error.remediation) > 0


class TestConvenienceFunction:
    """Tests for the module-level convenience function."""

    @pytest.mark.asyncio
    async def test_execute_via_gateway_requires_token_when_auth_required(self):
        """Convenience function requires token_bundle when spec requires auth."""
        spec = create_test_spec(auth_mode="bearer")

        result = await execute_via_gateway(
            sandbox_url=SANDBOX_URL,
            message=MESSAGE,
            session_key=SESSION_KEY,
            token_bundle=None,  # No token bundle
            spec=spec,
        )

        # Should fail-closed with AUTH_FAILED
        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == GatewayErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_execute_via_gateway_succeeds_without_token_when_no_auth(self):
        """Convenience function succeeds without token when spec has no auth."""
        spec = create_test_spec(auth_mode="none")

        with patch.object(
            ZeroclawGatewayService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = GatewayResult(
                success=True, output={"output": "test response"}
            )

            result = await execute_via_gateway(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=None,
                spec=spec,
            )

            assert result.success is True
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_via_gateway_creates_service_with_token_bundle(self):
        """Convenience function creates service and executes with token bundle."""
        spec = create_test_spec()

        with patch.object(
            ZeroclawGatewayService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = GatewayResult(
                success=True, output={"output": "test response"}
            )

            result = await execute_via_gateway(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
                workspace_id=WORKSPACE_ID,
                agent_pack_id=AGENT_PACK_ID,
                run_id=RUN_ID,
                spec=spec,
            )

            assert result.success is True
            mock_execute.assert_called_once()


class TestConfiguration:
    """Tests for configuration loading."""

    def test_default_configuration(self):
        """Service initializes with sensible defaults."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        assert service.health_timeout == 10
        assert service.health_retries == 3
        assert service.health_backoff == 1.0
        assert service.execute_timeout == 300
        assert service.execute_retries == 0

    def test_custom_configuration(self):
        """Service accepts custom configuration."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(
            spec=spec,
            health_timeout=5,
            health_retries=1,
            health_backoff=0.5,
            execute_timeout=60,
            execute_retries=2,
        )

        assert service.health_timeout == 5
        assert service.health_retries == 1
        assert service.health_backoff == 0.5
        assert service.execute_timeout == 60
        assert service.execute_retries == 2

    def test_spec_driven_paths(self):
        """Service uses paths from spec."""
        spec = create_test_spec()
        spec.gateway.health_path = "/custom/health/path"
        spec.gateway.execute_path = "/custom/execute/path"
        service = ZeroclawGatewayService(spec=spec)

        # Verify the service stores the spec
        assert service.spec.gateway.health_path == "/custom/health/path"
        assert service.spec.gateway.execute_path == "/custom/execute/path"


class TestTokenBundle:
    """Tests for sandbox-scoped token bundle authentication."""

    def test_token_bundle_current_token(self):
        """Token bundle returns current token for authentication."""
        bundle = GatewayTokenBundle(current="token-123")
        assert bundle.get_effective_token() == "token-123"

    def test_token_bundle_grace_token_valid(self):
        """Grace token is valid during grace period."""
        from datetime import datetime, timedelta

        future_time = datetime.utcnow() + timedelta(seconds=30)
        bundle = GatewayTokenBundle(
            current="token-new",
            previous="token-old",
            previous_expires_at=future_time,
        )
        assert bundle.is_grace_token_valid() is True
        assert bundle.get_effective_token(attempt=1) == "token-old"

    def test_token_bundle_grace_token_expired(self):
        """Grace token is rejected after expiry."""
        from datetime import datetime, timedelta

        past_time = datetime.utcnow() - timedelta(seconds=1)
        bundle = GatewayTokenBundle(
            current="token-new",
            previous="token-old",
            previous_expires_at=past_time,
        )
        assert bundle.is_grace_token_valid() is False
        assert bundle.get_effective_token(attempt=1) == "token-new"

    def test_token_bundle_no_grace_token(self):
        """Token bundle without previous token uses current on retry."""
        bundle = GatewayTokenBundle(current="token-only")
        assert bundle.is_grace_token_valid() is False
        assert bundle.get_effective_token(attempt=0) == "token-only"
        assert bundle.get_effective_token(attempt=1) == "token-only"


class TestSpecDrivenRequest:
    """Tests for spec-driven request transformation."""

    @pytest.mark.asyncio
    async def test_request_uses_spec_example_structure(self):
        """Execute request uses spec example as base template."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)

        # Mock health and execute
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        mock_execute_response = AsyncMock(spec=httpx.Response)
        mock_execute_response.status_code = 200
        mock_execute_response.json.return_value = {"output": "test"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.return_value = mock_execute_response

            await service.execute(
                sandbox_url=SANDBOX_URL,
                message="Custom message",
                session_key="session-abc",
                token_bundle=TEST_TOKEN_BUNDLE,
                workspace_id="ws-123",
                sender_id="user-456",
            )

            # Verify request structure
            call_args = mock_post.call_args
            request_json = call_args.kwargs.get("json", {})

            assert request_json["message"] == "Custom message"
            assert request_json["context"]["session_id"] == "session-abc"
            assert request_json["context"]["sender_id"] == "user-456"
            assert request_json["context"]["workspace_id"] == "ws-123"

    @pytest.mark.asyncio
    async def test_execute_uses_spec_execute_path(self):
        """Execute uses execute_path from spec."""
        spec = create_test_spec()
        spec.gateway.execute_path = "/custom/execute"
        service = ZeroclawGatewayService(spec=spec)

        # Mock health and execute
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        mock_execute_response = AsyncMock(spec=httpx.Response)
        mock_execute_response.status_code = 200
        mock_execute_response.json.return_value = {"output": "test"}

        with (
            patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get,
            patch.object(
                httpx.AsyncClient, "post", new_callable=AsyncMock
            ) as mock_post,
        ):
            mock_get.return_value = mock_health_response
            mock_post.return_value = mock_execute_response

            await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
            )

            # Verify correct URL was called
            call_args = mock_post.call_args
            assert "/custom/execute" in call_args.args[0]
