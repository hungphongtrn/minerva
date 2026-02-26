"""Service-level tests for Picoclaw bridge service.

These tests verify:
1. Health is polled before execution
2. Bearer token is attached to requests
3. Health/auth failures short-circuit execute path
4. Timeout and retry behavior is bounded
5. Error typing is stable for API mapping

Uses mocked HTTP transport - does not require live sandbox runtime.
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from src.services.picoclaw_bridge_service import (
    PicoclawBridgeService,
    BridgeErrorType,
    BridgeResult,
    BridgeTokenBundle,
    execute_via_bridge,
)


# Constants for tests
SANDBOX_URL = "http://sandbox:18790"
MESSAGE = "Hello, agent!"
SESSION_KEY = "minerva:workspace-123:pack-456:run-789"
WORKSPACE_ID = "workspace-123"
AGENT_PACK_ID = "pack-456"
RUN_ID = "run-789"
TEST_TOKEN_BUNDLE = BridgeTokenBundle(current="test-token-current")


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_check_health_returns_healthy_on_200(self):
        """Health check returns healthy status on 200 response."""
        service = PicoclawBridgeService()

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
        service = PicoclawBridgeService()

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
        service = PicoclawBridgeService()

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
        service = PicoclawBridgeService()

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")

            status = await service.check_health(SANDBOX_URL)

            assert status.healthy is False
            assert status.status == "timeout"


class TestHealthPolling:
    """Tests for health polling with retries."""

    @pytest.mark.asyncio
    async def test_poll_health_succeeds_on_first_attempt(self):
        """Poll returns healthy on first successful health check."""
        service = PicoclawBridgeService(health_retries=3, health_backoff=0.01)

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
        service = PicoclawBridgeService(health_retries=3, health_backoff=0.01)

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
        service = PicoclawBridgeService(health_retries=2, health_backoff=0.01)

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
    async def test_bearer_token_attached_to_health_request(self):
        """Bearer token is attached to health check requests when token_bundle provided."""
        service = PicoclawBridgeService()

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
    async def test_bearer_token_attached_to_execute_request(self):
        """Bearer token is attached to execute requests with token_bundle."""
        service = PicoclawBridgeService()

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


class TestFailClosed:
    """Tests for fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_execute_blocked_when_health_fails(self):
        """Execute is blocked when health check fails."""
        service = PicoclawBridgeService(health_retries=1, health_backoff=0.01)

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
            assert result.error.error_type == BridgeErrorType.HEALTH_CHECK_FAILED

    @pytest.mark.asyncio
    async def test_execute_blocked_on_auth_failure(self):
        """Execute is blocked when authentication fails."""
        service = PicoclawBridgeService(health_retries=1, health_backoff=0.01)

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
            assert result.error.error_type == BridgeErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_no_execute_attempted_when_health_fails(self):
        """Verify execute endpoint is never called when health fails."""
        service = PicoclawBridgeService(health_retries=1, health_backoff=0.01)

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
        service = PicoclawBridgeService(
            health_retries=0, execute_timeout=5, health_backoff=0.01
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
            assert result.error.error_type == BridgeErrorType.TIMEOUT
            assert "timed out" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_health_timeout_returns_typed_error(self):
        """Health check returns typed error on timeout."""
        service = PicoclawBridgeService(health_timeout=5)

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
        service = PicoclawBridgeService(
            health_retries=0, execute_retries=2, health_backoff=0.01
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
        service = PicoclawBridgeService(
            health_retries=0, execute_retries=2, health_backoff=0.01
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
        service = PicoclawBridgeService(
            health_retries=0, execute_timeout=5, health_backoff=0.01
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

            assert result.error.error_type == BridgeErrorType.TRANSPORT_ERROR

    @pytest.mark.asyncio
    async def test_malformed_response_returns_typed_error(self):
        """Malformed JSON responses return MALFORMED_RESPONSE type."""
        service = PicoclawBridgeService(
            health_retries=0, execute_retries=0, health_backoff=0.01
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

            assert result.error.error_type == BridgeErrorType.MALFORMED_RESPONSE

    @pytest.mark.asyncio
    async def test_error_includes_remediation(self):
        """Errors include remediation guidance."""
        service = PicoclawBridgeService(
            health_retries=0, execute_timeout=5, health_backoff=0.01
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
    async def test_execute_via_bridge_requires_token_bundle(self):
        """Convenience function requires token_bundle for authentication."""
        result = await execute_via_bridge(
            sandbox_url=SANDBOX_URL,
            message=MESSAGE,
            session_key=SESSION_KEY,
            token_bundle=None,  # No token bundle
        )

        # Should fail-closed with AUTH_FAILED
        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == BridgeErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_execute_via_bridge_creates_service_with_token_bundle(self):
        """Convenience function creates service and executes with token bundle."""
        with patch.object(
            PicoclawBridgeService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = BridgeResult(
                success=True, output={"output": "test response"}
            )

            result = await execute_via_bridge(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=TEST_TOKEN_BUNDLE,
                workspace_id=WORKSPACE_ID,
                agent_pack_id=AGENT_PACK_ID,
                run_id=RUN_ID,
            )

            assert result.success is True
            mock_execute.assert_called_once()


class TestConfiguration:
    """Tests for configuration loading."""

    def test_default_configuration(self):
        """Service initializes with sensible defaults."""
        service = PicoclawBridgeService()

        assert service.health_timeout == 10
        assert service.health_retries == 3
        assert service.health_backoff == 1.0
        assert service.execute_timeout == 300
        assert service.execute_retries == 0

    def test_custom_configuration(self):
        """Service accepts custom configuration."""
        service = PicoclawBridgeService(
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


class TestTokenBundle:
    """Tests for sandbox-scoped token bundle authentication."""

    def test_token_bundle_current_token(self):
        """Token bundle returns current token for authentication."""
        bundle = BridgeTokenBundle(current="token-123")
        assert bundle.get_effective_token() == "token-123"

    def test_token_bundle_grace_token_valid(self):
        """Grace token is valid during grace period."""
        from datetime import datetime, timedelta

        future_time = datetime.utcnow() + timedelta(seconds=30)
        bundle = BridgeTokenBundle(
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
        bundle = BridgeTokenBundle(
            current="token-new",
            previous="token-old",
            previous_expires_at=past_time,
        )
        assert bundle.is_grace_token_valid() is False
        assert bundle.get_effective_token(attempt=1) == "token-new"

    def test_token_bundle_no_grace_token(self):
        """Token bundle without previous token uses current on retry."""
        bundle = BridgeTokenBundle(current="token-only")
        assert bundle.is_grace_token_valid() is False
        assert bundle.get_effective_token(attempt=0) == "token-only"
        assert bundle.get_effective_token(attempt=1) == "token-only"


class TestSandboxScopedAuth:
    """Tests for per-sandbox token authentication."""

    @pytest.mark.asyncio
    async def test_execute_requires_token_bundle(self):
        """Execute requires token_bundle and fails-closed without it."""
        service = PicoclawBridgeService()

        result = await service.execute(
            sandbox_url=SANDBOX_URL,
            message=MESSAGE,
            session_key=SESSION_KEY,
            token_bundle=None,
        )

        # Should fail-closed with AUTH_FAILED
        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == BridgeErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_health_check_without_token_succeeds(self):
        """Health check without token proceeds (may return 401 from upstream)."""
        service = PicoclawBridgeService()

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            # No token_bundle passed
            status = await service.check_health(SANDBOX_URL, token_bundle=None)

            # Should proceed without auth header
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" not in headers
            assert status.healthy is True

    @pytest.mark.asyncio
    async def test_token_rotation_uses_current_first(self):
        """First attempt uses current token, not grace token."""
        from datetime import datetime, timedelta

        service = PicoclawBridgeService()

        future_time = datetime.utcnow() + timedelta(seconds=30)
        bundle = BridgeTokenBundle(
            current="token-current",
            previous="token-previous",
            previous_expires_at=future_time,
        )

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await service.check_health(SANDBOX_URL, token_bundle=bundle)

            # First attempt should use current token
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert headers["Authorization"] == "Bearer token-current"
