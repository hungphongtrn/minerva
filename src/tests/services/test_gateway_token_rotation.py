"""Tests for token rotation grace fallback behavior.

These tests verify:
1. Health check retries with grace token on 401/403
2. Execute retries with grace token on 401/403
3. Grace token is only used when still valid
4. AUTH_FAILED when both tokens fail

Uses mocked HTTP transport - does not require live sandbox runtime.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
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
    GatewayTokenBundle,
)


# Constants for tests
SANDBOX_URL = "http://sandbox:18790"
MESSAGE = "Hello, agent!"
SESSION_KEY = "minerva:workspace-123:pack-456:run-789"


def create_test_spec(auth_mode: str = "bearer") -> ZeroclawSpec:
    """Create a test ZeroclawSpec with specified auth mode."""
    return ZeroclawSpec(
        version="1.0.0",
        gateway=GatewaySpec(
            port=18790,
            health_path="/health",
            execute_path="/webhook",
            stream_mode="none",
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


def create_valid_grace_bundle() -> GatewayTokenBundle:
    """Create a token bundle with a valid grace token."""
    future_time = datetime.utcnow() + timedelta(seconds=30)
    return GatewayTokenBundle(
        current="token-current",
        previous="token-previous",
        previous_expires_at=future_time,
    )


def create_expired_grace_bundle() -> GatewayTokenBundle:
    """Create a token bundle with an expired grace token."""
    past_time = datetime.utcnow() - timedelta(seconds=1)
    return GatewayTokenBundle(
        current="token-current",
        previous="token-previous",
        previous_expires_at=past_time,
    )


def create_no_grace_bundle() -> GatewayTokenBundle:
    """Create a token bundle with no grace token."""
    return GatewayTokenBundle(current="token-current")


class TestHealthGraceFallback:
    """Tests for health check grace-token fallback behavior."""

    @pytest.mark.asyncio
    async def test_health_retries_with_grace_token_on_401(self):
        """Health check retries with grace token when current token returns 401."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)
        token_bundle = create_valid_grace_bundle()

        # First call returns 401, second call (with grace token) returns 200
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [mock_401_response, mock_200_response]

            status = await service.check_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is True
            assert status.status == "ok"
            assert mock_request.call_count == 2

            # Verify first call used current token
            first_call = mock_request.call_args_list[0]
            first_headers = first_call.kwargs.get("headers", {})
            assert first_headers.get("Authorization") == "Bearer token-current"

            # Verify second call used previous/grace token
            second_call = mock_request.call_args_list[1]
            second_headers = second_call.kwargs.get("headers", {})
            assert second_headers.get("Authorization") == "Bearer token-previous"

    @pytest.mark.asyncio
    async def test_health_retries_with_grace_token_on_403(self):
        """Health check retries with grace token when current token returns 403."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)
        token_bundle = create_valid_grace_bundle()

        # First call returns 403, second call (with grace token) returns 200
        mock_403_response = AsyncMock(spec=httpx.Response)
        mock_403_response.status_code = 403

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [mock_403_response, mock_200_response]

            status = await service.check_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is True
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_health_no_fallback_when_grace_token_expired(self):
        """Health check does not retry with grace token when it has expired."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)
        token_bundle = create_expired_grace_bundle()

        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_401_response

            status = await service.check_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is False
            assert status.status == "unauthorized"
            # Should only make 1 call (no retry with expired grace token)
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_health_no_fallback_when_no_grace_token(self):
        """Health check does not retry when no grace token exists."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)
        token_bundle = create_no_grace_bundle()

        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_401_response

            status = await service.check_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is False
            assert status.status == "unauthorized"
            # Should only make 1 call (no retry without grace token)
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_health_auth_failed_when_both_tokens_fail(self):
        """Health check returns unauthorized when both tokens return 401."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec)
        token_bundle = create_valid_grace_bundle()

        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_401_response

            status = await service.check_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is False
            assert status.status == "unauthorized"
            # Should make 2 calls (current token fails, grace token also fails)
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_poll_health_succeeds_with_grace_fallback(self):
        """poll_health() succeeds when grace token fallback works."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0)
        token_bundle = create_valid_grace_bundle()

        # First call returns 401, second call returns 200
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"status": "ok"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [mock_401_response, mock_200_response]

            status = await service.poll_health(SANDBOX_URL, token_bundle=token_bundle)

            assert status.healthy is True
            assert mock_request.call_count == 2


class TestExecuteGraceFallback:
    """Tests for execute grace-token fallback behavior."""

    @pytest.mark.asyncio
    async def test_execute_retries_with_grace_token_on_401(self):
        """Execute retries with grace token when current token returns 401."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_valid_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # First execute returns 401, second (with grace token) returns 200
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"output": "success"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,  # health check
                mock_401_response,  # execute with current token
                mock_200_response,  # execute with grace token
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is True
            assert result.output == {"output": "success"}

            # Verify execute calls: first with current, second with grace
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 2

            first_headers = post_calls[0].kwargs.get("headers", {})
            assert first_headers.get("Authorization") == "Bearer token-current"

            second_headers = post_calls[1].kwargs.get("headers", {})
            assert second_headers.get("Authorization") == "Bearer token-previous"

    @pytest.mark.asyncio
    async def test_execute_retries_with_grace_token_on_403(self):
        """Execute retries with grace token when current token returns 403."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_valid_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # First execute returns 403, second (with grace token) returns 200
        mock_403_response = AsyncMock(spec=httpx.Response)
        mock_403_response.status_code = 403

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"output": "success"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_403_response,
                mock_200_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is True
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 2

    @pytest.mark.asyncio
    async def test_execute_no_fallback_when_grace_token_expired(self):
        """Execute does not retry with grace token when it has expired."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_expired_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Execute returns 401
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_401_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is False
            assert result.error.error_type == GatewayErrorType.AUTH_FAILED

            # Should only be 1 POST call (no retry with expired grace token)
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_no_fallback_when_no_grace_token(self):
        """Execute does not retry when no grace token exists."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_no_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Execute returns 401
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_401_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is False
            assert result.error.error_type == GatewayErrorType.AUTH_FAILED

            # Should only be 1 POST call (no retry without grace token)
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_auth_failed_when_both_tokens_fail(self):
        """Execute returns AUTH_FAILED when both tokens return 401."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_valid_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Both execute attempts return 401
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_401_response,  # current token fails
                mock_401_response,  # grace token also fails
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is False
            assert result.error.error_type == GatewayErrorType.AUTH_FAILED

            # Should be 2 POST calls (current fails, grace also fails)
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 2

    @pytest.mark.asyncio
    async def test_execute_grace_fallback_independent_of_execute_retries(self):
        """Grace fallback happens even when execute_retries is 0."""
        spec = create_test_spec()
        # Set execute_retries to 0 - grace fallback should still work
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_valid_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # First execute returns 401, second (grace) returns 200
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"output": "success"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_401_response,
                mock_200_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            # Should succeed via grace token fallback
            assert result.success is True
            # 1 health + 2 execute = 3 calls
            assert mock_request.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_only_one_grace_fallback_attempt(self):
        """Execute only attempts grace fallback once per request."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=1)
        token_bundle = create_valid_grace_bundle()

        # Health passes
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Both current and grace tokens return 401
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_401_response,  # current token fails
                mock_401_response,  # grace token fails
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is False
            # Should be 2 POST calls (current + grace), no additional retries
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 2


class TestGraceFallbackEdgeCases:
    """Tests for edge cases in grace-token fallback behavior."""

    @pytest.mark.asyncio
    async def test_no_auth_fallback_when_spec_has_no_auth(self):
        """No auth fallback when spec has no auth mode."""
        spec = create_test_spec(auth_mode="none")
        service = ZeroclawGatewayService(spec=spec, health_retries=0, execute_retries=0)
        token_bundle = create_valid_grace_bundle()

        # Health passes (without auth)
        mock_health_response = AsyncMock(spec=httpx.Response)
        mock_health_response.status_code = 200
        mock_health_response.json.return_value = {"status": "ok"}

        # Execute succeeds
        mock_200_response = AsyncMock(spec=httpx.Response)
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"output": "success"}

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                mock_health_response,
                mock_200_response,
            ]

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            assert result.success is True
            # Verify no Authorization headers were sent
            for call in mock_request.call_args_list:
                headers = call.kwargs.get("headers", {})
                assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_health_blocked_when_auth_fails_and_no_grace(self):
        """Health check blocks execution when auth fails and no valid grace token."""
        spec = create_test_spec()
        service = ZeroclawGatewayService(spec=spec, health_retries=0)
        token_bundle = create_expired_grace_bundle()

        # Health returns 401
        mock_401_response = AsyncMock(spec=httpx.Response)
        mock_401_response.status_code = 401

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_401_response

            result = await service.execute(
                sandbox_url=SANDBOX_URL,
                message=MESSAGE,
                session_key=SESSION_KEY,
                token_bundle=token_bundle,
            )

            # Should fail with AUTH_FAILED due to health check
            assert result.success is False
            assert result.error.error_type == GatewayErrorType.AUTH_FAILED
            # Should only have health check calls, no execute
            post_calls = [c for c in mock_request.call_args_list if c.args[0] == "POST"]
            assert len(post_calls) == 0
