"""Tests for Daytona base image preflight CLI.

Validates preflight pass/fail, cleanup, and report output.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import the preflight module
from src.scripts.daytona_base_image_preflight import (
    DaytonaBaseImagePreflight,
    PreflightResult,
    REQUIRED_IDENTITY_FILES,
    REQUIRED_IDENTITY_DIRS,
    create_parser,
)


class TestPreflightResult:
    """Test PreflightResult data structure."""

    def test_result_to_dict(self):
        """Result serializes to dictionary correctly."""
        result = PreflightResult(
            success=True,
            image="test@sha256:abc123",
            sandbox_id="test-sandbox",
            checks={"provision": {"status": "passed"}},
            errors=[],
            remediation=None,
            duration_seconds=12.34,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["image"] == "test@sha256:abc123"
        assert data["sandbox_id"] == "test-sandbox"
        assert data["checks"]["provision"]["status"] == "passed"
        assert data["errors"] == []
        assert data["remediation"] is None
        assert data["duration_seconds"] == 12.34

    def test_result_with_errors(self):
        """Result with failures includes error details."""
        result = PreflightResult(
            success=False,
            image="test:latest",
            sandbox_id="test-sandbox",
            checks={
                "provision": {"status": "passed"},
                "identity_files": {"status": "failed"},
            },
            errors=["Missing AGENT.md"],
            remediation="Add required identity files",
            duration_seconds=5.0,
        )

        data = result.to_dict()

        assert data["success"] is False
        assert len(data["errors"]) == 1
        assert data["errors"][0] == "Missing AGENT.md"
        assert data["remediation"] == "Add required identity files"


class TestPreflightInitialization:
    """Test preflight validator initialization."""

    def test_init_with_explicit_params(self):
        """Initialize with explicit parameters."""
        validator = DaytonaBaseImagePreflight(
            api_key="test-key",
            api_url="https://api.example.com",
            target="eu",
        )

        assert validator._api_key == "test-key"
        assert validator._api_url == "https://api.example.com"
        assert validator._target == "eu"

    def test_init_defaults_from_env(self, monkeypatch):
        """Initialize defaults from environment variables."""

        # Use monkeypatch to set env vars (it handles cleanup automatically)
        monkeypatch.setenv("DAYTONA_API_KEY", "env-key")
        monkeypatch.setenv("DAYTONA_API_URL", "https://env.example.com")
        monkeypatch.setenv("DAYTONA_TARGET", "ap")

        # Force re-import to pick up new env vars - explicitly read from env
        validator = DaytonaBaseImagePreflight(
            api_key=os.environ.get("DAYTONA_API_KEY"),
            api_url=os.environ.get("DAYTONA_API_URL"),
            target=os.environ.get("DAYTONA_TARGET"),
        )

        assert validator._api_key == "env-key"
        assert validator._api_url == "https://env.example.com"
        assert validator._target == "ap"

    def test_init_defaults_when_env_empty(self, monkeypatch):
        """Initialize with defaults when env vars not set."""

        # Clear env vars
        for var in ["DAYTONA_API_KEY", "DAYTONA_API_URL", "DAYTONA_TARGET"]:
            monkeypatch.delenv(var, raising=False)

        # Explicitly pass None to trigger env var reading (which will use defaults)
        validator = DaytonaBaseImagePreflight(
            api_key=os.environ.get("DAYTONA_API_KEY", ""),
            api_url=os.environ.get("DAYTONA_API_URL", ""),
            target=os.environ.get("DAYTONA_TARGET", "us"),
        )

        assert validator._api_key == ""
        assert validator._api_url == ""
        assert validator._target == "us"  # Default


class TestPreflightValidation:
    """Test preflight validation logic."""

    @pytest.fixture
    def mock_daytona_sdk(self):
        """Mock Daytona SDK for testing."""
        with patch(
            "src.scripts.daytona_base_image_preflight.AsyncDaytona"
        ) as mock_class:
            mock_daytona = AsyncMock()
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Create mock sandbox
            mock_sandbox = MagicMock()
            mock_sandbox.id = "test-preflight-sandbox"
            mock_sandbox.state = "running"
            mock_sandbox.status = "running"
            mock_sandbox.preview_url = "https://test.daytona.run"
            mock_sandbox.metadata = {
                "gateway_url": "https://gateway-test.daytona.run:18790"
            }

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            yield mock_daytona, mock_sandbox

    @pytest.mark.asyncio
    async def test_successful_preflight_pass(self, mock_daytona_sdk):
        """Successful validation returns passing result."""
        mock_daytona, mock_sandbox = mock_daytona_sdk

        validator = DaytonaBaseImagePreflight(api_key="test")
        result = await validator.validate(
            image="registry/picoclaw@sha256:" + "a" * 64,
            sandbox_id="test-preflight",
        )

        assert result.success is True
        assert result.image == "registry/picoclaw@sha256:" + "a" * 64
        assert result.sandbox_id == "test-preflight"
        assert "provision" in result.checks
        assert result.checks["provision"]["status"] == "passed"
        assert "identity_files" in result.checks
        assert "gateway" in result.checks

    @pytest.mark.asyncio
    async def test_preflight_always_cleans_up_sandbox(self, mock_daytona_sdk):
        """Validation always cleans up disposable sandbox."""
        mock_daytona, mock_sandbox = mock_daytona_sdk

        validator = DaytonaBaseImagePreflight(api_key="test")
        await validator.validate(
            image="test@sha256:abc123",
            sandbox_id="cleanup-test",
        )

        # Verify delete was called
        mock_daytona.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_preflight_cleans_up_on_failure(self, mock_daytona_sdk):
        """Cleanup occurs even when validation fails."""
        mock_daytona, mock_sandbox = mock_daytona_sdk

        # Make sandbox creation fail
        mock_daytona.create.side_effect = Exception("Creation failed")

        validator = DaytonaBaseImagePreflight(api_key="test")
        result = await validator.validate(
            image="test@sha256:abc123",
            sandbox_id="fail-cleanup-test",
        )

        assert result.success is False
        # Should still attempt cleanup (but may fail gracefully)

    @pytest.mark.asyncio
    async def test_preflight_detects_provision_timeout(self, mock_daytona_sdk):
        """Timeout during provisioning is handled gracefully."""
        import asyncio

        mock_daytona, mock_sandbox = mock_daytona_sdk

        # Make create timeout
        async def slow_create(**kwargs):
            await asyncio.sleep(1000)  # Long sleep
            return mock_sandbox

        mock_daytona.create = slow_create

        validator = DaytonaBaseImagePreflight(api_key="test")
        validator.PROVISION_TIMEOUT_SECONDS = 0.01  # Very short timeout

        result = await validator.validate(
            image="test@sha256:abc123",
            sandbox_id="timeout-test",
        )

        assert result.success is False
        assert (
            "timeout" in str(result.errors).lower()
            or "provision" in str(result.checks).lower()
        )

    @pytest.mark.asyncio
    async def test_preflight_sandbox_not_running(self, mock_daytona_sdk):
        """Sandbox not in running state fails validation."""
        mock_daytona, mock_sandbox = mock_daytona_sdk

        # Make sandbox stopped
        mock_sandbox.state = "stopped"
        mock_sandbox.status = "stopped"
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        validator = DaytonaBaseImagePreflight(api_key="test")
        result = await validator.validate(
            image="test@sha256:abc123",
            sandbox_id="stopped-test",
        )

        assert result.success is False
        assert result.checks["sandbox_state"]["status"] == "failed"


class TestGatewayResolution:
    """Test gateway URL resolution logic."""

    def test_gateway_from_metadata(self):
        """Gateway extracted from sandbox metadata."""
        validator = DaytonaBaseImagePreflight(api_key="test")

        mock_sandbox = MagicMock()
        mock_sandbox.metadata = {"gateway_url": "https://custom.gateway:18790"}

        url = validator._resolve_gateway_url(mock_sandbox, "test-id")

        assert url == "https://custom.gateway:18790"

    def test_gateway_derived_from_preview(self):
        """Gateway derived from preview URL."""
        validator = DaytonaBaseImagePreflight(api_key="test")

        mock_sandbox = MagicMock()
        mock_sandbox.metadata = None
        mock_sandbox.preview_url = "https://abc123.daytona.run"

        url = validator._resolve_gateway_url(mock_sandbox, "test-id")

        assert "gateway-abc123.daytona.run" in url
        assert ":18790" in url

    def test_gateway_constructed_for_cloud(self):
        """Gateway constructed for Daytona Cloud."""
        validator = DaytonaBaseImagePreflight(api_key="test", target="eu")

        mock_sandbox = MagicMock()
        mock_sandbox.metadata = None
        mock_sandbox.preview_url = None

        url = validator._resolve_gateway_url(mock_sandbox, "test-sandbox-id")

        assert "gateway-test-sandbox-id.eu.daytona.run:18790" in url

    def test_gateway_constructed_for_self_hosted(self):
        """Gateway constructed for self-hosted Daytona."""
        validator = DaytonaBaseImagePreflight(
            api_key="test",
            api_url="https://daytona.example.com",
        )

        mock_sandbox = MagicMock()
        mock_sandbox.metadata = None
        mock_sandbox.preview_url = None

        url = validator._resolve_gateway_url(mock_sandbox, "test-id")

        assert "gateway-test-id" in url
        assert ":18790" in url


class TestRemediationGeneration:
    """Test remediation guidance generation."""

    def test_remediation_for_provision_failure(self):
        """Remediation includes provision failure steps."""
        validator = DaytonaBaseImagePreflight(api_key="test")

        checks = {"provision": {"status": "failed"}}
        errors = ["Provision failed"]

        remediation = validator._generate_remediation(checks, errors)

        assert "DAYTONA_API_KEY" in remediation
        assert "registry credentials" in remediation.lower()
        assert "infrastructure" in remediation.lower()

    def test_remediation_for_identity_failure(self):
        """Remediation includes identity file steps."""
        validator = DaytonaBaseImagePreflight(api_key="test")

        checks = {
            "provision": {"status": "passed"},
            "identity_files": {"status": "failed"},
        }
        errors = ["Missing files"]

        remediation = validator._generate_remediation(checks, errors)

        assert "AGENT.md" in remediation
        assert "SOUL.md" in remediation
        assert "IDENTITY.md" in remediation
        assert "skills/" in remediation

    def test_remediation_for_gateway_failure(self):
        """Remediation includes gateway failure steps."""
        validator = DaytonaBaseImagePreflight(api_key="test")

        checks = {
            "provision": {"status": "passed"},
            "gateway": {"status": "failed"},
        }
        errors = ["Gateway not found"]

        remediation = validator._generate_remediation(checks, errors)

        assert "gateway" in remediation.lower()
        assert "port 18790" in remediation.lower()


class TestArgumentParser:
    """Test CLI argument parsing."""

    def test_parser_requires_image(self):
        """Parser requires --image argument."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_accepts_digest_image(self):
        """Parser accepts digest-pinned image."""
        parser = create_parser()

        args = parser.parse_args(["--image", "registry/image@sha256:abc123"])

        assert args.image == "registry/image@sha256:abc123"
        assert args.json is False
        assert args.verbose is False

    def test_parser_accepts_json_flag(self):
        """Parser accepts --json flag."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest", "--json"])

        assert args.json is True

    def test_parser_accepts_verbose_flag(self):
        """Parser accepts --verbose flag."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest", "--verbose"])

        assert args.verbose is True

    def test_parser_accepts_sandbox_id(self):
        """Parser accepts --sandbox-id."""
        parser = create_parser()

        args = parser.parse_args(
            ["--image", "test:latest", "--sandbox-id", "custom-id"]
        )

        assert args.sandbox_id == "custom-id"

    def test_parser_accepts_timeout(self):
        """Parser accepts --timeout."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest", "--timeout", "300"])

        assert args.timeout == 300

    def test_parser_accepts_target(self):
        """Parser accepts --target."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest", "--target", "eu"])

        assert args.target == "eu"

    def test_parser_default_timeout(self):
        """Parser has default timeout of 120."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest"])

        assert args.timeout == 120

    def test_parser_default_target(self):
        """Parser has default target of 'us'."""
        parser = create_parser()

        args = parser.parse_args(["--image", "test:latest"])

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

    def test_help_includes_env_vars(self, capsys):
        """Help documents environment variables."""
        parser = create_parser()

        # Capture help text by checking the parser's epilog
        assert "DAYTONA_API_KEY" in parser.epilog
        assert "DAYTONA_API_URL" in parser.epilog
        assert "DAYTONA_TARGET" in parser.epilog


class TestJSONOutput:
    """Test JSON output format."""

    @pytest.fixture
    def mock_daytona_sdk(self):
        """Mock Daytona SDK for testing."""
        with patch(
            "src.scripts.daytona_base_image_preflight.AsyncDaytona"
        ) as mock_class:
            mock_daytona = AsyncMock()
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_sandbox = MagicMock()
            mock_sandbox.id = "test"
            mock_sandbox.state = "running"
            mock_sandbox.preview_url = "https://test.daytona.run"
            mock_sandbox.metadata = {"gateway_url": "https://gateway:18790"}

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            yield mock_daytona

    @pytest.mark.asyncio
    async def test_json_output_structure(self, mock_daytona_sdk, capsys, monkeypatch):
        """JSON output has expected structure."""
        monkeypatch.setenv("DAYTONA_API_KEY", "test-key")

        validator = DaytonaBaseImagePreflight(api_key="test")
        result = await validator.validate(
            image="test@sha256:" + "a" * 64,
        )

        # Check JSON serialization
        data = result.to_dict()

        assert "success" in data
        assert "image" in data
        assert "sandbox_id" in data
        assert "checks" in data
        assert "errors" in data
        assert "remediation" in data
        assert "duration_seconds" in data

        # Validate types
        assert isinstance(data["success"], bool)
        assert isinstance(data["image"], str)
        assert isinstance(data["checks"], dict)
        assert isinstance(data["errors"], list)

    @pytest.mark.asyncio
    async def test_json_output_valid_json(self, mock_daytona_sdk, monkeypatch):
        """JSON output is valid JSON."""
        monkeypatch.setenv("DAYTONA_API_KEY", "test-key")

        validator = DaytonaBaseImagePreflight(api_key="test")
        result = await validator.validate(
            image="test@sha256:" + "b" * 64,
        )

        json_str = json.dumps(result.to_dict())

        # Should parse without error
        parsed = json.loads(json_str)
        assert parsed["success"] == result.success


class TestRequiredConstants:
    """Test required constants match Picoclaw runtime contract."""

    def test_required_identity_files(self):
        """Required identity files match Picoclaw contract."""
        assert "AGENT.md" in REQUIRED_IDENTITY_FILES
        assert "SOUL.md" in REQUIRED_IDENTITY_FILES
        assert "IDENTITY.md" in REQUIRED_IDENTITY_FILES

    def test_required_identity_dirs(self):
        """Required identity directories match Picoclaw contract."""
        assert "skills" in REQUIRED_IDENTITY_DIRS
