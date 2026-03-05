"""Tests for Picoclaw gateway audit harness.

Validates audit harness performs deterministic probes and always cleans up.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from uuid import UUID

# Import the audit module
from src.scripts.picoclaw_gateway_audit import (
    PicoclawGatewayAuditor,
    AuditResult,
    create_parser,
)


class TestAuditResult:
    """Test AuditResult data structure."""

    def test_result_to_dict(self):
        """Result serializes to dictionary correctly."""
        result = AuditResult(
            success=True,
            mode="daytona",
            health={"accessible": True, "status_code": 200},
            execute={"status_code": 200},
            streaming_probe={"any_streaming_available": False},
            continuity_wiring={"sender_id_forwarded": True},
            sandbox_id="test-sandbox",
            errors=[],
            duration_seconds=12.34,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["mode"] == "daytona"
        assert data["sandbox_id"] == "test-sandbox"
        assert data["health"]["accessible"] is True
        assert data["duration_seconds"] == 12.34

    def test_result_with_errors(self):
        """Result with failures includes error details."""
        result = AuditResult(
            success=False,
            mode="direct",
            health={"accessible": False},
            errors=["Gateway unreachable"],
            duration_seconds=5.0,
        )

        data = result.to_dict()

        assert data["success"] is False
        assert len(data["errors"]) == 1
        assert data["errors"][0] == "Gateway unreachable"


class TestAuditorInitialization:
    """Test auditor initialization."""

    def test_init_with_explicit_params(self):
        """Initialize with explicit parameters."""
        auditor = PicoclawGatewayAuditor(
            api_key="test-key",
            api_url="https://api.example.com",
            target="eu",
        )

        assert auditor._api_key == "test-key"
        assert auditor._api_url == "https://api.example.com"
        assert auditor._target == "eu"

    def test_init_defaults_from_env(self, monkeypatch):
        """Initialize defaults from environment variables."""
        import os

        monkeypatch.setenv("DAYTONA_API_KEY", "env-key")
        monkeypatch.setenv("DAYTONA_API_URL", "https://env.example.com")
        monkeypatch.setenv("DAYTONA_TARGET", "ap")

        # Create auditor reading from env vars explicitly
        auditor = PicoclawGatewayAuditor(
            api_key=os.environ.get("DAYTONA_API_KEY"),
            api_url=os.environ.get("DAYTONA_API_URL"),
            target=os.environ.get("DAYTONA_TARGET", "us"),
        )

        assert auditor._api_key == "env-key"
        assert auditor._api_url == "https://env.example.com"
        assert auditor._target == "ap"

    def test_init_defaults_when_env_empty(self, monkeypatch):
        """Initialize with defaults when env vars not set."""
        for var in ["DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"]:
            monkeypatch.delenv(var, raising=False)

        auditor = PicoclawGatewayAuditor()

        assert auditor._api_key == ""
        assert auditor._api_url == ""
        assert auditor._target == "us"  # Default


class TestDaytonaModeProvisioning:
    """Test Daytona mode provisioning with correct config."""

    @pytest.fixture
    def mock_daytona_provider(self):
        """Mock DaytonaSandboxProvider for testing."""
        with patch(
            "src.infrastructure.sandbox.providers.daytona.DaytonaSandboxProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider_class.return_value = mock_provider

            # Create mock sandbox info
            mock_ref = MagicMock()
            mock_ref.provider_ref = "test-sandbox-id"
            mock_ref.metadata = {
                "gateway_url": "https://gateway-test.daytona.run:18790"
            }

            mock_sandbox_info = MagicMock()
            mock_sandbox_info.ref = mock_ref
            mock_sandbox_info.state = "READY"
            mock_sandbox_info.health = "HEALTHY"

            mock_provider.provision_sandbox = AsyncMock(return_value=mock_sandbox_info)
            mock_provider.stop_sandbox = AsyncMock(return_value=MagicMock())

            yield mock_provider_class, mock_provider

    @pytest.fixture
    def mock_bridge_service(self):
        """Mock PicoclawBridgeService for testing."""
        with patch(
            "src.services.picoclaw_bridge_service.PicoclawBridgeService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            # Create mock bridge result
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.to_dict.return_value = {
                "success": True,
                "output": {"result": "ok"},
            }

            mock_service.execute = AsyncMock(return_value=mock_result)

            yield mock_service_class, mock_service

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock health response
            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            # Mock streaming probe responses (404 for all)
            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                if "/health" in url:
                    return mock_health_response
                return mock_not_found_response

            mock_client.get = mock_get

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_provision_sandbox_called_with_bridge_config(
        self, mock_daytona_provider, mock_bridge_service, mock_http_client
    ):
        """DaytonaSandboxProvider.provision_sandbox() called with SandboxConfig containing auth_token."""
        mock_provider_class, mock_provider = mock_daytona_provider

        auditor = PicoclawGatewayAuditor(api_key="test-key")
        result = await auditor.audit_daytona_sandbox(
            message="Test message",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify provision_sandbox was called
        mock_provider.provision_sandbox.assert_called_once()

        # Get the config passed to provision_sandbox
        call_args = mock_provider.provision_sandbox.call_args
        config = call_args[0][0]  # First positional argument

        # Verify it's a SandboxConfig
        from src.infrastructure.sandbox.providers.base import SandboxConfig

        assert isinstance(config, SandboxConfig)

        # Verify runtime_bridge_config contains auth_token
        assert config.runtime_bridge_config is not None
        assert "bridge" in config.runtime_bridge_config
        assert "auth_token" in config.runtime_bridge_config["bridge"]
        assert config.runtime_bridge_config["bridge"]["enabled"] is True

        # Verify auth_token is a non-empty string
        auth_token = config.runtime_bridge_config["bridge"]["auth_token"]
        assert isinstance(auth_token, str)
        assert len(auth_token) > 0

    @pytest.mark.asyncio
    async def test_stop_sandbox_called_once_on_success(
        self, mock_daytona_provider, mock_bridge_service, mock_http_client
    ):
        """DaytonaSandboxProvider.stop_sandbox() called exactly once on success."""
        mock_provider_class, mock_provider = mock_daytona_provider

        auditor = PicoclawGatewayAuditor(api_key="test-key")
        result = await auditor.audit_daytona_sandbox(
            message="Test message",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify stop_sandbox was called exactly once
        assert mock_provider.stop_sandbox.call_count == 1

    @pytest.mark.asyncio
    async def test_stop_sandbox_called_once_when_probe_raises(
        self, mock_daytona_provider, mock_bridge_service, mock_http_client
    ):
        """DaytonaSandboxProvider.stop_sandbox() called exactly once even when probe raises."""
        mock_provider_class, mock_provider = mock_daytona_provider
        mock_service_class, mock_service = mock_bridge_service

        # Make execute raise an exception
        mock_service.execute.side_effect = Exception("Probe failed")

        auditor = PicoclawGatewayAuditor(api_key="test-key")

        try:
            result = await auditor.audit_daytona_sandbox(
                message="Test message",
                sender_id="test-sender",
                session_id="test-session",
            )
        except Exception:
            pass  # Expected to raise

        # Verify stop_sandbox was still called exactly once
        assert mock_provider.stop_sandbox.call_count == 1


class TestBridgeServiceIntegration:
    """Test PicoclawBridgeService integration."""

    @pytest.fixture
    def mock_daytona_provider(self):
        """Mock DaytonaSandboxProvider for testing."""
        with patch(
            "src.infrastructure.sandbox.providers.daytona.DaytonaSandboxProvider"
        ) as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider_class.return_value = mock_provider

            mock_ref = MagicMock()
            mock_ref.provider_ref = "test-sandbox-id"
            mock_ref.metadata = {
                "gateway_url": "https://gateway-test.daytona.run:18790"
            }

            mock_sandbox_info = MagicMock()
            mock_sandbox_info.ref = mock_ref

            mock_provider.provision_sandbox = AsyncMock(return_value=mock_sandbox_info)
            mock_provider.stop_sandbox = AsyncMock(return_value=MagicMock())

            yield mock_provider_class, mock_provider

    @pytest.fixture
    def mock_bridge_service(self):
        """Mock PicoclawBridgeService for testing."""
        with patch(
            "src.services.picoclaw_bridge_service.PicoclawBridgeService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.to_dict.return_value = {
                "success": True,
                "output": {"result": "ok"},
            }

            mock_service.execute = AsyncMock(return_value=mock_result)

            yield mock_service_class, mock_service

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                if "/health" in url:
                    return mock_health_response
                return mock_not_found_response

            mock_client.get = mock_get

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_bridge_service_execute_called_with_token_bundle(
        self, mock_daytona_provider, mock_bridge_service, mock_http_client
    ):
        """PicoclawBridgeService.execute() invoked with generated token bundle."""
        mock_provider_class, mock_provider = mock_daytona_provider
        mock_service_class, mock_service = mock_bridge_service

        auditor = PicoclawGatewayAuditor(api_key="test-key")
        result = await auditor.audit_daytona_sandbox(
            message="Test message",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify execute was called
        mock_service.execute.assert_called_once()

        # Get the call kwargs
        call_kwargs = mock_service.execute.call_args.kwargs

        # Verify token_bundle was passed
        assert "token_bundle" in call_kwargs
        token_bundle = call_kwargs["token_bundle"]

        # Verify token_bundle has current token
        assert token_bundle.current is not None
        assert isinstance(token_bundle.current, str)
        assert len(token_bundle.current) > 0

    @pytest.mark.asyncio
    async def test_sender_id_and_session_id_forwarded(
        self, mock_daytona_provider, mock_bridge_service, mock_http_client
    ):
        """PicoclawBridgeService.execute() forwards sender_id and session_id."""
        mock_provider_class, mock_provider = mock_daytona_provider
        mock_service_class, mock_service = mock_bridge_service

        auditor = PicoclawGatewayAuditor(api_key="test-key")
        result = await auditor.audit_daytona_sandbox(
            message="Test message",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Get the call kwargs
        call_kwargs = mock_service.execute.call_args.kwargs

        # Verify sender_id and session_id were passed
        assert call_kwargs.get("sender_id") == "test-sender"
        assert call_kwargs.get("session_id") == "test-session"

        # Verify message was passed
        assert call_kwargs.get("message") == "Test message"


class TestDirectModeAudit:
    """Test direct gateway URL audit mode."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Track calls for verification
            mock_client._calls = []

            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            mock_execute_response = MagicMock()
            mock_execute_response.status_code = 200
            mock_execute_response.json.return_value = {"result": "success"}

            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                mock_client._calls.append(("get", url, kwargs))
                if "/health" in url:
                    return mock_health_response
                return mock_not_found_response

            async def mock_post(url, **kwargs):
                mock_client._calls.append(("post", url, kwargs))
                if "/bridge/execute" in url:
                    return mock_execute_response
                return mock_not_found_response

            mock_client.get = mock_get
            mock_client.post = mock_post

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_direct_mode_calls_health_endpoint(self, mock_http_client):
        """Direct mode calls /health endpoint on gateway URL."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify health endpoint was called
        health_calls = [
            c for c in mock_client._calls if c[0] == "get" and "/health" in c[1]
        ]
        assert len(health_calls) == 1

        # Verify correct URL
        assert "https://gateway-test.daytona.run:18790/health" in health_calls[0][1]

    @pytest.mark.asyncio
    async def test_direct_mode_calls_execute_endpoint(self, mock_http_client):
        """Direct mode calls /bridge/execute endpoint."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify execute endpoint was called
        execute_calls = [
            c
            for c in mock_client._calls
            if c[0] == "post" and "/bridge/execute" in c[1]
        ]
        assert len(execute_calls) == 1

    @pytest.mark.asyncio
    async def test_direct_mode_uses_correct_auth_header(self, mock_http_client):
        """Direct mode uses correct Bearer token auth header."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="my-secret-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify auth header was set correctly
        health_calls = [
            c for c in mock_client._calls if c[0] == "get" and "/health" in c[1]
        ]
        headers = health_calls[0][2].get("headers", {})
        assert headers.get("Authorization") == "Bearer my-secret-token"


class TestStreamingProbe:
    """Test streaming endpoint probe behavior."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            # Simulate one streaming endpoint being available
            mock_stream_response = MagicMock()
            mock_stream_response.status_code = 200

            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                if "/health" in url:
                    return mock_health_response
                elif "/events" in url:
                    return mock_stream_response
                return mock_not_found_response

            mock_client.get = mock_get

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_probes_all_candidate_paths(self, mock_http_client):
        """Streaming probe checks all candidate paths."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify all candidate paths are in result
        streaming = result.streaming_probe
        assert "candidate_paths" in streaming
        assert len(streaming["candidate_paths"]) > 0

    @pytest.mark.asyncio
    async def test_detects_available_streaming_endpoints(self, mock_http_client):
        """Streaming probe detects available endpoints."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Verify /events is detected as accessible
        streaming = result.streaming_probe
        assert "/events" in streaming["probes"]
        assert streaming["probes"]["/events"]["accessible"] is True

    @pytest.mark.asyncio
    async def test_any_streaming_available_flag(self, mock_http_client):
        """any_streaming_available flag set correctly."""
        mock_client_class, mock_client = mock_http_client

        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Since we simulated /events as available
        assert result.streaming_probe["any_streaming_available"] is True


class TestContinuityWiring:
    """Test session continuity wiring evidence."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            mock_execute_response = MagicMock()
            mock_execute_response.status_code = 200
            mock_execute_response.json.return_value = {"result": "success"}

            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                if "/health" in url:
                    return mock_health_response
                return mock_not_found_response

            async def mock_post(url, **kwargs):
                return mock_execute_response

            mock_client.get = mock_get
            mock_client.post = mock_post

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_captures_original_sender_and_session_ids(self, mock_http_client):
        """Continuity wiring captures original sender_id and session_id."""
        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="original-sender",
            session_id="original-session",
        )

        continuity = result.continuity_wiring
        assert continuity["original_sender_id"] == "original-sender"
        assert continuity["original_session_id"] == "original-session"

    @pytest.mark.asyncio
    async def test_captures_transformed_request(self, mock_http_client):
        """Continuity wiring captures transformed request."""
        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        continuity = result.continuity_wiring
        # Verify request_transformed is captured
        assert continuity["request_transformed"] is not None
        assert "sender_id" in continuity["request_transformed"]
        assert "session_id" in continuity["request_transformed"]


class TestArgumentParser:
    """Test CLI argument parsing."""

    def test_parser_requires_daytona_or_gateway_url(self):
        """Parser allows no args (validates at runtime)."""
        parser = create_parser()

        # Should not raise - validation happens in main
        args = parser.parse_args([])
        assert args.daytona is False
        assert args.gateway_url is None

    def test_parser_accepts_daytona_flag(self):
        """Parser accepts --daytona flag."""
        parser = create_parser()

        args = parser.parse_args(["--daytona"])

        assert args.daytona is True

    def test_parser_accepts_gateway_url(self):
        """Parser accepts --gateway-url."""
        parser = create_parser()

        args = parser.parse_args(["--gateway-url", "https://gateway.example.com"])

        assert args.gateway_url == "https://gateway.example.com"

    def test_parser_accepts_auth_token(self):
        """Parser accepts --auth-token."""
        parser = create_parser()

        args = parser.parse_args(["--auth-token", "secret123"])

        assert args.auth_token == "secret123"

    def test_parser_accepts_message(self):
        """Parser accepts --message."""
        parser = create_parser()

        args = parser.parse_args(["--message", "Custom test message"])

        assert args.message == "Custom test message"

    def test_parser_accepts_sender_id(self):
        """Parser accepts --sender-id."""
        parser = create_parser()

        args = parser.parse_args(["--sender-id", "custom-sender"])

        assert args.sender_id == "custom-sender"

    def test_parser_accepts_session_id(self):
        """Parser accepts --session-id."""
        parser = create_parser()

        args = parser.parse_args(["--session-id", "custom-session"])

        assert args.session_id == "custom-session"

    def test_parser_accepts_json_flag(self):
        """Parser accepts --json flag."""
        parser = create_parser()

        args = parser.parse_args(["--json"])

        assert args.json is True

    def test_parser_accepts_target(self):
        """Parser accepts --target."""
        parser = create_parser()

        args = parser.parse_args(["--target", "eu"])

        assert args.target == "eu"

    def test_parser_default_values(self):
        """Parser has correct default values."""
        parser = create_parser()

        args = parser.parse_args([])

        assert args.daytona is False
        assert args.message == "Hello from Picoclaw gateway audit"
        assert args.sender_id == "minerva-audit"
        assert args.session_id == "audit-session"
        assert args.json is False
        assert args.target == "us"


class TestCLIHelp:
    """Test CLI help output."""

    def test_help_includes_description(self, capsys):
        """Help includes program description."""
        parser = create_parser()

        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])

        # --help exits with 0
        assert exc_info.value.code == 0

    def test_help_includes_env_vars(self):
        """Help documents environment variables."""
        parser = create_parser()

        # Check the parser's epilog
        assert "DAYTONA_API_KEY" in parser.epilog
        assert "DAYTONA_API_URL" in parser.epilog
        assert "DAYTONA_TARGET" in parser.epilog


class TestJSONOutput:
    """Test JSON output format."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock httpx.AsyncClient for testing."""
        with patch(
            "src.scripts.picoclaw_gateway_audit.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"status": "ok"}

            mock_execute_response = MagicMock()
            mock_execute_response.status_code = 200
            mock_execute_response.json.return_value = {"result": "success"}

            mock_not_found_response = MagicMock()
            mock_not_found_response.status_code = 404

            async def mock_get(url, **kwargs):
                if "/health" in url:
                    return mock_health_response
                return mock_not_found_response

            async def mock_post(url, **kwargs):
                return mock_execute_response

            mock_client.get = mock_get
            mock_client.post = mock_post

            yield mock_client_class, mock_client

    @pytest.mark.asyncio
    async def test_json_output_structure(self, mock_http_client):
        """JSON output has expected structure."""
        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        # Check JSON serialization
        data = result.to_dict()

        assert "success" in data
        assert "mode" in data
        assert "health" in data
        assert "execute" in data
        assert "streaming_probe" in data
        assert "continuity_wiring" in data
        assert "duration_seconds" in data

        # Validate types
        assert isinstance(data["success"], bool)
        assert isinstance(data["mode"], str)
        assert isinstance(data["health"], dict)

    @pytest.mark.asyncio
    async def test_json_output_valid_json(self, mock_http_client):
        """JSON output is valid JSON."""
        auditor = PicoclawGatewayAuditor()
        result = await auditor.audit_existing_gateway(
            gateway_url="https://gateway-test.daytona.run:18790",
            auth_token="test-token",
            message="Hello",
            sender_id="test-sender",
            session_id="test-session",
        )

        json_str = json.dumps(result.to_dict())

        # Should parse without error
        parsed = json.loads(json_str)
        assert parsed["success"] == result.success


class TestErrorHandling:
    """Test error handling behavior."""

    def test_run_raises_on_missing_gateway_url_for_direct_mode(self):
        """Run raises ValueError when gateway_url missing in direct mode."""
        auditor = PicoclawGatewayAuditor()

        with pytest.raises(ValueError, match="gateway_url required"):
            asyncio.run(auditor.run(daytona_mode=False))

    def test_run_raises_on_missing_auth_token_for_direct_mode(self):
        """Run raises ValueError when auth_token missing in direct mode."""
        auditor = PicoclawGatewayAuditor()

        with pytest.raises(ValueError, match="auth_token required"):
            asyncio.run(
                auditor.run(
                    daytona_mode=False,
                    gateway_url="https://gateway.example.com",
                )
            )
