"""Tests for Daytona volume mount wiring and per-sandbox config writes.

Tests verify:
- Provider passes CreateSandboxFromSnapshotParams with volume mount at /workspace/pack
- verify_identity_files() uses sandbox.fs.get_file_info for real file checks
- provision_sandbox() writes config via fs.create_folder and fs.upload_file
- Config path is outside /workspace/pack (per-sandbox, not shared)
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from daytona import DaytonaError

from src.infrastructure.sandbox.providers.base import SandboxConfig
from src.infrastructure.sandbox.providers.daytona import (
    DaytonaSandboxProvider,
    IdentityVerificationResult,
    SandboxProvisionError,
)


@pytest.fixture
def provider():
    """Create a Daytona provider for testing."""
    return DaytonaSandboxProvider(
        api_key="test-api-key",
        snapshot_name="picoclaw-test-snapshot",
    )


@pytest.fixture
def create_mock_sandbox():
    """Factory for creating mock Daytona sandbox objects."""

    def _create(
        sandbox_id: str = "test-sandbox-id",
        state: str = "started",
        status: str = "healthy",
    ):
        mock = MagicMock()
        mock.id = sandbox_id
        mock.state = state
        mock.status = status
        mock.preview_url = f"https://{sandbox_id}.daytona.run"

        # Mock file system operations
        mock.fs = MagicMock()
        mock.fs.get_file_info = AsyncMock(return_value=MagicMock(is_dir=False))
        mock.fs.create_folder = AsyncMock()
        mock.fs.upload_file = AsyncMock()

        # Mock process operations for workspace symlink creation
        mock.process = MagicMock()
        mock.process.exec = AsyncMock(return_value="")

        return mock

    return _create


class TestVolumeMountWiring:
    """Tests for volume mount configuration in provisioning."""

    @pytest.mark.asyncio
    async def test_provision_mounts_volume_at_workspace_pack(
        self, provider, create_mock_sandbox
    ):
        """Provider mounts pack volume at /workspace/pack via CreateSandboxFromSnapshotParams."""
        workspace_id = uuid4()
        pack_id = uuid4()
        pack_digest = "a" * 64

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path="/test/pack",
            agent_pack_id=pack_id,
            pack_digest=pack_digest,
        )

        mock_sandbox = create_mock_sandbox()

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.volume = MagicMock()
            mock_volume = MagicMock()
            mock_volume.id = "volume-id-123"
            mock_volume.state = "ready"
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                await provider.provision_sandbox(config)

            # Verify create was called with CreateSandboxFromSnapshotParams
            mock_daytona.create.assert_called_once()
            call_args = mock_daytona.create.call_args[0]
            params = call_args[0]

            # Verify volume mount exists
            assert hasattr(params, "volumes")
            assert params.volumes is not None
            assert len(params.volumes) == 1

            volume_mount = params.volumes[0]
            assert volume_mount.mount_path == "/workspace/pack"

            # Volume mount should use Daytona volume ID
            assert volume_mount.volume_id == "volume-id-123"

            # Pack volume must be read-only (isolation contract enforcement)
            read_only = getattr(volume_mount, "read_only", None)
            if read_only is None:
                read_only = getattr(volume_mount, "readonly", None)
            if read_only is None and hasattr(volume_mount, "additional_properties"):
                read_only = volume_mount.additional_properties.get("read_only")
            if read_only is None and hasattr(volume_mount, "additional_properties"):
                read_only = volume_mount.additional_properties.get("readonly")
            assert read_only is True, f"Pack volume must be read-only, got: {read_only}"

    @pytest.mark.asyncio
    async def test_provision_without_pack_does_not_mount_volume(
        self, provider, create_mock_sandbox
    ):
        """Provider does not mount volume when no pack_source_path provided."""
        workspace_id = uuid4()

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=None,  # No pack
        )

        mock_sandbox = create_mock_sandbox()

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.volume = MagicMock()
            mock_daytona.volume.get = AsyncMock()

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                await provider.provision_sandbox(config)

            # Verify create was called
            mock_daytona.create.assert_called_once()
            call_args = mock_daytona.create.call_args[0]
            params = call_args[0]

            # No volumes should be mounted
            assert params.volumes is None or len(params.volumes) == 0
            mock_daytona.volume.get.assert_not_called()


class TestWorkspaceSymlinkPermissions:
    """Tests for workspace permission preflight during symlink setup."""

    @pytest.mark.asyncio
    async def test_create_workspace_symlinks_runs_writable_preflight(
        self, provider, create_mock_sandbox
    ):
        """Provider repairs/checks workspace writability before creating symlinks."""
        mock_sandbox = create_mock_sandbox()

        await provider._create_workspace_symlinks(mock_sandbox)

        commands = [call.args[0] for call in mock_sandbox.process.exec.await_args_list]
        assert len(commands) == 5
        assert "test -w /workspace" in commands[0]
        assert "chown $(id -u):$(id -g) /workspace" in commands[0]
        assert "chmod u+rwx /workspace" in commands[0]
        assert commands[1] == "ln -sf /workspace/pack/AGENT.md /workspace/AGENT.md"

    @pytest.mark.asyncio
    async def test_create_workspace_symlinks_falls_back_to_home_workspace(
        self, provider
    ):
        """Provider falls back to HOME/workspace if /workspace is not writable."""
        mock_sandbox = MagicMock()
        mock_sandbox.env = {"HOME": "/home/picoclaw"}
        mock_sandbox.process = MagicMock()
        mock_sandbox.process.exec = AsyncMock(
            side_effect=[
                MagicMock(exit_code=1, stderr="Permission denied", result=""),
                MagicMock(exit_code=0, stderr="", result=""),
                MagicMock(exit_code=0, stderr="", result=""),
                MagicMock(exit_code=0, stderr="", result=""),
                MagicMock(exit_code=0, stderr="", result=""),
                MagicMock(exit_code=0, stderr="", result=""),
            ]
        )

        workspace_path = await provider._create_workspace_symlinks(mock_sandbox)

        commands = [call.args[0] for call in mock_sandbox.process.exec.await_args_list]
        assert workspace_path == "/home/picoclaw/workspace"
        assert "test -w /workspace" in commands[0]
        assert "test -w /home/picoclaw/workspace" in commands[1]
        assert (
            commands[2]
            == "ln -sf /workspace/pack/AGENT.md /home/picoclaw/workspace/AGENT.md"
        )

    @pytest.mark.asyncio
    async def test_create_workspace_symlinks_fails_with_clear_message_when_not_writable(
        self, provider
    ):
        """Provider raises explicit error when workspace remains non-writable."""
        mock_sandbox = MagicMock()
        mock_sandbox.process = MagicMock()
        mock_sandbox.process.exec = AsyncMock(
            return_value=MagicMock(exit_code=1, stderr="Permission denied", result="")
        )

        with pytest.raises(SandboxProvisionError) as exc_info:
            await provider._create_workspace_symlinks(mock_sandbox)

        assert "Workspace path is not writable after repair attempt" in str(
            exc_info.value
        )


class TestIdentityFileVerification:
    """Tests for real identity file verification via file API."""

    @pytest.mark.asyncio
    async def test_verify_identity_files_checks_required_files(self, provider):
        """verify_identity_files uses sandbox.fs.get_file_info for required files."""
        sandbox_id = "test-sandbox-id"

        mock_sandbox = MagicMock()
        mock_sandbox.state = "started"

        # Mock file info for required files (all exist)
        file_info = MagicMock()
        file_info.is_dir = False

        dir_info = MagicMock()
        dir_info.is_dir = True

        mock_sandbox.fs = MagicMock()
        mock_sandbox.fs.get_file_info = AsyncMock(
            side_effect=lambda path: (dir_info if "skills" in path else file_info)
        )

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.get = AsyncMock(return_value=mock_sandbox)

            result = await provider.verify_identity_files(sandbox_id)

            # Should be ready since all files exist
            assert result.ready is True
            assert result.missing_files == []

            # Verify get_file_info was called for each required file
            expected_calls = [
                "/workspace/AGENT.md",
                "/workspace/SOUL.md",
                "/workspace/IDENTITY.md",
                "/workspace/skills",
            ]
            actual_calls = [
                call[0][0] for call in mock_sandbox.fs.get_file_info.call_args_list
            ]
            for expected in expected_calls:
                assert expected in actual_calls, f"Missing call for {expected}"

    @pytest.mark.asyncio
    async def test_verify_identity_files_fails_when_file_missing(self, provider):
        """Verification fails when a required file is missing."""
        sandbox_id = "test-sandbox-id"

        mock_sandbox = MagicMock()
        mock_sandbox.state = "started"

        # Mock file info - AGENT.md is missing
        file_info = MagicMock()
        file_info.is_dir = False

        dir_info = MagicMock()
        dir_info.is_dir = True

        call_count = [0]

        async def mock_get_file_info(path: str):
            call_count[0] += 1
            if "AGENT.md" in path:
                raise DaytonaError("File not found")
            if "skills" in path:
                return dir_info
            return file_info

        mock_sandbox.fs = MagicMock()
        mock_sandbox.fs.get_file_info = mock_get_file_info

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.get = AsyncMock(return_value=mock_sandbox)

            result = await provider.verify_identity_files(sandbox_id, timeout=0.1)

            # Should not be ready since AGENT.md is missing
            assert result.ready is False

    @pytest.mark.asyncio
    async def test_verify_identity_files_fails_when_skills_not_dir(self, provider):
        """Verification fails when skills exists but is not a directory."""
        sandbox_id = "test-sandbox-id"

        mock_sandbox = MagicMock()
        mock_sandbox.state = "started"

        # Mock file info - skills is a file, not a directory
        file_info = MagicMock()
        file_info.is_dir = False

        mock_sandbox.fs = MagicMock()
        mock_sandbox.fs.get_file_info = AsyncMock(return_value=file_info)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.get = AsyncMock(return_value=mock_sandbox)

            result = await provider.verify_identity_files(sandbox_id, timeout=0.1)

            # Should not be ready since skills is not a directory
            assert result.ready is False

    @pytest.mark.asyncio
    async def test_verify_identity_files_waits_until_sandbox_running(self, provider):
        """Verification polls through creating state and succeeds when running."""
        sandbox_id = "test-sandbox-id"

        creating_sandbox = MagicMock()
        creating_sandbox.state = "creating"
        creating_sandbox.fs = MagicMock()
        creating_sandbox.fs.get_file_info = AsyncMock()

        running_sandbox = MagicMock()
        running_sandbox.state = "started"

        file_info = MagicMock()
        file_info.is_dir = False
        dir_info = MagicMock()
        dir_info.is_dir = True

        running_sandbox.fs = MagicMock()
        running_sandbox.fs.get_file_info = AsyncMock(
            side_effect=lambda path: (dir_info if "skills" in path else file_info)
        )

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # First poll sees creating, second poll sees started
            mock_daytona.get = AsyncMock(
                side_effect=[creating_sandbox, running_sandbox]
            )

            result = await provider.verify_identity_files(sandbox_id, timeout=1.5)

            assert result.ready is True
            assert mock_daytona.get.await_count >= 2


class TestPerSandboxConfigWrite:
    """Tests for per-sandbox config.json write via file API."""

    @pytest.mark.asyncio
    async def test_provision_creates_config_outside_pack_volume(
        self, provider, create_mock_sandbox
    ):
        """Config is written outside /workspace/pack (per-sandbox, not shared)."""
        workspace_id = uuid4()
        pack_id = uuid4()
        pack_digest = "a" * 64

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path="/test/pack",
            agent_pack_id=pack_id,
            pack_digest=pack_digest,
            runtime_bridge_config={
                "bridge": {"enabled": True, "auth_token": "test-token"},
                "workspace_id": str(workspace_id),
            },
        )

        mock_sandbox = create_mock_sandbox()

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            # Patch identity verification
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
                patch.object(
                    provider, "_start_bridge_runtime", new_callable=AsyncMock
                ) as mock_start_runtime,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )
                mock_start_runtime.return_value = True

                result = await provider.provision_sandbox(config)

            # Verify create_folder was called for config directory
            mock_sandbox.fs.create_folder.assert_called_once()
            folder_call = mock_sandbox.fs.create_folder.call_args[0]
            assert folder_call[0] == "/home/daytona/.picoclaw"

            # Verify upload_file was called for config.json
            mock_sandbox.fs.upload_file.assert_called_once()
            upload_call = mock_sandbox.fs.upload_file.call_args[0]
            config_path = upload_call[1]

            # Config path must be outside /workspace/pack
            assert not config_path.startswith("/workspace/pack"), (
                f"Config path {config_path} must be outside /workspace/pack"
            )
            assert config_path == "/home/daytona/.picoclaw/config.json"

            # Verify metadata includes config path
            assert result.ref.metadata.get("materialized_config_path") == config_path

    @pytest.mark.asyncio
    async def test_provision_config_contains_bridge_settings(
        self, provider, create_mock_sandbox
    ):
        """Config contains bridge settings from runtime_bridge_config."""
        workspace_id = uuid4()
        pack_id = uuid4()

        runtime_config: Dict[str, Any] = {
            "bridge": {
                "enabled": True,
                "auth_token": "secret-token-123",
                "gateway_port": 18790,
            },
            "workspace_id": str(workspace_id),
        }

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path="/test/pack",
            agent_pack_id=pack_id,
            pack_digest="a" * 64,
            runtime_bridge_config=runtime_config,
        )

        mock_sandbox = create_mock_sandbox()
        uploaded_content: bytes = b""

        async def capture_upload(content: bytes, path: str):
            nonlocal uploaded_content
            uploaded_content = content

        mock_sandbox.fs.upload_file = capture_upload

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            # Patch identity verification
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
                patch.object(
                    provider, "_start_bridge_runtime", new_callable=AsyncMock
                ) as mock_start_runtime,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )
                mock_start_runtime.return_value = True

                await provider.provision_sandbox(config)

            # Parse uploaded config
            config_data = json.loads(uploaded_content.decode("utf-8"))

            # Verify bridge settings
            assert config_data["channels"]["bridge"]["enabled"] is True
            assert config_data["channels"]["bridge"]["auth_token"] == "secret-token-123"
            assert config_data["gateway"]["port"] == 18790

            # Verify public channels are disabled
            assert config_data["channels"]["telegram"]["enabled"] is False
            assert config_data["channels"]["discord"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_provision_handles_existing_config_dir(
        self, provider, create_mock_sandbox
    ):
        """Provisioning succeeds if config directory already exists."""
        workspace_id = uuid4()
        pack_id = uuid4()

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path="/test/pack",
            agent_pack_id=pack_id,
            pack_digest="a" * 64,
        )

        mock_sandbox = create_mock_sandbox()

        # Simulate "already exists" error for create_folder
        async def mock_create_folder(path: str, mode: str):
            raise DaytonaError("Directory already exists")

        mock_sandbox.fs.create_folder = mock_create_folder

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            # Patch identity verification
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                # Should succeed even though directory exists
                result = await provider.provision_sandbox(config)

                from src.infrastructure.sandbox.providers.base import SandboxState

                assert result.state == SandboxState.READY

    @pytest.mark.asyncio
    async def test_provision_returns_gateway_url_in_metadata(
        self, provider, create_mock_sandbox
    ):
        """Provision result exposes gateway_url metadata for orchestrator persistence."""
        workspace_id = uuid4()
        gateway_url = "https://gateway-test-sandbox-id.us.daytona.run:18790"

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=None,
        )

        mock_sandbox = create_mock_sandbox(sandbox_id="test-sandbox-id")

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = gateway_url

                result = await provider.provision_sandbox(config)

            assert result.ref.metadata.get("gateway_url") == gateway_url


class TestWorkspaceFallbackRuntimeConfigPath:
    """Tests for runtime config path behavior with workspace fallback."""

    def test_resolve_runtime_config_path_uses_effective_workspace(self, provider):
        """Provider rewrites /workspace runtime config path to fallback workspace."""
        resolved = provider._resolve_runtime_config_path(
            "/workspace/.zeroclaw/config.json",
            "/home/picoclaw/workspace",
        )

        assert resolved == "/home/picoclaw/workspace/.zeroclaw/config.json"

    @pytest.mark.asyncio
    async def test_start_bridge_runtime_substitutes_fallback_config_path(
        self, provider
    ):
        """Bridge start command uses the effective config path when provided."""
        mock_sandbox = MagicMock()

        with (
            patch.object(
                provider,
                "_is_bridge_listening",
                new=AsyncMock(side_effect=[False, True]),
            ),
            patch.object(
                provider,
                "_exec_checked",
                new_callable=AsyncMock,
            ) as mock_exec_checked,
        ):
            mock_exec_checked.return_value = {}
            started = await provider._start_bridge_runtime(
                mock_sandbox,
                strict=True,
                config_path="/home/picoclaw/workspace/.zeroclaw/config.json",
            )

        assert started is True
        start_cmd = mock_exec_checked.await_args.args[1]
        assert "/home/picoclaw/workspace/.zeroclaw/config.json" in start_cmd
        assert "--config /workspace/.zeroclaw/config.json" not in start_cmd

    @pytest.mark.asyncio
    async def test_provision_uses_fallback_path_for_config_write_and_start(
        self, provider, create_mock_sandbox
    ):
        """Provisioning writes config and starts runtime with fallback config path."""
        workspace_id = uuid4()
        config = SandboxConfig(
            workspace_id=workspace_id,
            runtime_bridge_config={
                "bridge": {"enabled": True, "auth_token": "test-token"},
                "workspace_id": str(workspace_id),
            },
        )

        mock_sandbox = create_mock_sandbox()

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            with (
                patch.object(
                    provider,
                    "_create_workspace_symlinks",
                    new=AsyncMock(return_value="/home/picoclaw/workspace"),
                ),
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
                patch.object(
                    provider, "_start_bridge_runtime", new_callable=AsyncMock
                ) as mock_start_runtime,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )
                mock_start_runtime.return_value = True

                result = await provider.provision_sandbox(config)

        mock_sandbox.fs.create_folder.assert_called_once_with(
            "/home/picoclaw/workspace/.zeroclaw",
            "700",
        )
        upload_path = mock_sandbox.fs.upload_file.call_args[0][1]
        assert upload_path == "/home/picoclaw/workspace/.zeroclaw/config.json"

        assert (
            mock_start_runtime.await_args.kwargs["config_path"]
            == "/home/picoclaw/workspace/.zeroclaw/config.json"
        )
        assert (
            result.ref.metadata.get("materialized_config_path")
            == "/home/picoclaw/workspace/.zeroclaw/config.json"
        )
