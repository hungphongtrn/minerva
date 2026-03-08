"""Tests for Daytona snapshot build service and CLI command.

Tests cover:
- Configuration validation
- Repository cloning
- Image building from Dockerfile
- Snapshot creation via Daytona SDK
- Error handling and remediation
- CLI command integration
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.daytona_snapshot_build_service import (
    DaytonaSnapshotBuildService,
    SnapshotBuildError,
    SnapshotBuildResult,
)


class TestSnapshotBuildCLI:
    """Tests for snapshot build CLI command."""

    def test_cli_missing_required_env_vars(self, capsys):
        """CLI exits with error when required env vars are missing."""
        import argparse

        from src.cli.commands.snapshot_build import _handle_build

        # Clear all relevant env vars
        with patch.dict(
            os.environ,
            {
                "PICOCLAW_REPO_URL": "",
                "PICOCLAW_REPO_REF": "",
                "DAYTONA_PICOCLAW_SNAPSHOT_NAME": "",
            },
            clear=False,
        ):
            args = argparse.Namespace(
                repo_url=None,
                ref=None,
                name=None,
            )
            exit_code = _handle_build(args)

        assert exit_code != 0

        captured = capsys.readouterr()
        assert "Missing required configuration" in captured.err

    @patch("src.cli.commands.snapshot_build.asyncio.run")
    @patch("src.cli.commands.snapshot_build.DaytonaSnapshotBuildService")
    def test_cli_success(self, mock_service_class, mock_run, capsys):
        """CLI succeeds with valid configuration."""
        import argparse

        from src.cli.commands.snapshot_build import _handle_build

        # Mock service and result
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_result = SnapshotBuildResult(
            success=True,
            snapshot_name="test-snapshot",
        )
        mock_run.return_value = mock_result

        args = argparse.Namespace(
            repo_url="https://github.com/example/picoclaw",
            ref="main",
            name="test-snapshot",
        )
        exit_code = _handle_build(args)

        assert exit_code == 0

        # Verify service was created with CLI args
        mock_service_class.assert_called_once_with(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
            snapshot_name="test-snapshot",
        )

        # Verify build_snapshot was called with log handler
        assert mock_service.build_snapshot.called

    @patch("src.cli.commands.snapshot_build.asyncio.run")
    @patch("src.cli.commands.snapshot_build.DaytonaSnapshotBuildService")
    def test_cli_failure_with_error_message(self, mock_service_class, mock_run, capsys):
        """CLI exits with error and shows error message on failure."""
        import argparse

        from src.cli.commands.snapshot_build import _handle_build

        # Mock service and result
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_result = SnapshotBuildResult(
            success=False,
            snapshot_name="test-snapshot",
            error_message="Build failed",
            remediation="Check logs for details",
        )
        mock_run.return_value = mock_result

        args = argparse.Namespace(
            repo_url="https://github.com/example/picoclaw",
            ref="main",
            name="test-snapshot",
        )
        exit_code = _handle_build(args)

        assert exit_code != 0

        captured = capsys.readouterr()
        assert "Build failed" in captured.err
        assert "Check logs for details" in captured.err

    @patch("src.cli.commands.snapshot_build.asyncio.run")
    @patch("src.cli.commands.snapshot_build.DaytonaSnapshotBuildService")
    def test_cli_uses_env_vars_when_args_not_provided(
        self, mock_service_class, mock_run
    ):
        """CLI uses env vars when CLI args are not provided."""
        import argparse

        from src.cli.commands.snapshot_build import _handle_build

        # Mock service and result
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_result = SnapshotBuildResult(
            success=True,
            snapshot_name="env-snapshot",
        )
        mock_run.return_value = mock_result

        with patch.dict(
            os.environ,
            {
                "PICOCLAW_REPO_URL": "https://github.com/env/picoclaw",
                "PICOCLAW_REPO_REF": "env-branch",
                "DAYTONA_PICOCLAW_SNAPSHOT_NAME": "env-snapshot",
            },
        ):
            args = argparse.Namespace(
                repo_url=None,
                ref=None,
                name=None,
            )
            _handle_build(args)

        # Verify service was created with env var values
        mock_service_class.assert_called_once_with(
            repo_url=None,
            repo_ref=None,
            snapshot_name=None,
        )

    @patch("src.cli.commands.snapshot_build.asyncio.run")
    @patch("src.cli.commands.snapshot_build.DaytonaSnapshotBuildService")
    def test_cli_args_override_env_vars(self, mock_service_class, mock_run):
        """CLI args override env vars when both are present."""
        import argparse

        from src.cli.commands.snapshot_build import _handle_build

        # Mock service and result
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_result = SnapshotBuildResult(
            success=True,
            snapshot_name="cli-snapshot",
        )
        mock_run.return_value = mock_result

        with patch.dict(
            os.environ,
            {
                "PICOCLAW_REPO_URL": "https://github.com/env/picoclaw",
                "PICOCLAW_REPO_REF": "env-branch",
                "DAYTONA_PICOCLAW_SNAPSHOT_NAME": "env-snapshot",
            },
        ):
            args = argparse.Namespace(
                repo_url="https://github.com/cli/picoclaw",
                ref="cli-branch",
                name="cli-snapshot",
            )
            _handle_build(args)

        # Verify service was created with CLI arg values (not env vars)
        mock_service_class.assert_called_once_with(
            repo_url="https://github.com/cli/picoclaw",
            repo_ref="cli-branch",
            snapshot_name="cli-snapshot",
        )


class TestDaytonaSnapshotBuildService:
    """Tests for DaytonaSnapshotBuildService."""

    def test_init_with_defaults(self):
        """Service initializes with environment variable defaults."""
        with patch.dict(
            os.environ,
            {
                "PICOCLAW_REPO_URL": "https://github.com/example/picoclaw",
                "PICOCLAW_REPO_REF": "v1.0.0",
                "DAYTONA_PICOCLAW_SNAPSHOT_NAME": "test-snapshot",
            },
        ):
            service = DaytonaSnapshotBuildService()

            assert service.repo_url == "https://github.com/example/picoclaw"
            assert service.repo_ref == "v1.0.0"
            assert service.snapshot_name == "test-snapshot"

    def test_init_with_explicit_params(self):
        """Service uses explicit parameters over env vars."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/custom/picoclaw",
            repo_ref="custom-branch",
            snapshot_name="custom-snapshot",
        )

        assert service.repo_url == "https://github.com/custom/picoclaw"
        assert service.repo_ref == "custom-branch"
        assert service.snapshot_name == "custom-snapshot"

    def test_init_default_ref(self):
        """Service defaults repo_ref to 'main' if not specified."""
        with patch.dict(os.environ, {}, clear=True):
            service = DaytonaSnapshotBuildService()
            assert service.repo_ref == "main"

    def test_validate_config_missing_all(self):
        """Validation fails when all required config is missing."""
        service = DaytonaSnapshotBuildService(
            repo_url=None,
            repo_ref="main",
            snapshot_name=None,
        )

        with pytest.raises(SnapshotBuildError) as exc_info:
            service._validate_config()

        assert "Missing required configuration" in str(exc_info.value)
        assert "PICOCLAW_REPO_URL" in str(exc_info.value)
        assert "DAYTONA_PICOCLAW_SNAPSHOT_NAME" in str(exc_info.value)
        assert exc_info.value.remediation is not None

    def test_validate_config_missing_repo_url(self):
        """Validation fails when repo URL is missing."""
        service = DaytonaSnapshotBuildService(
            repo_url=None,
            snapshot_name="test-snapshot",
        )

        with pytest.raises(SnapshotBuildError) as exc_info:
            service._validate_config()

        assert "PICOCLAW_REPO_URL" in str(exc_info.value)

    def test_validate_config_missing_snapshot_name(self):
        """Validation fails when snapshot name is missing."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name=None,
        )

        with pytest.raises(SnapshotBuildError) as exc_info:
            service._validate_config()

        assert "DAYTONA_PICOCLAW_SNAPSHOT_NAME" in str(exc_info.value)

    def test_validate_config_success(self):
        """Validation passes with all required config."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        # Should not raise
        service._validate_config()

    @patch("subprocess.run")
    def test_clone_repo_success(self, mock_run, tmp_path):
        """Repository cloning succeeds."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
        )

        mock_run.return_value = MagicMock(returncode=0)

        # Should not raise
        service._clone_repo(tmp_path)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "clone" in args
        assert "--branch" in args
        assert "main" in args
        assert "--depth" in args
        assert "1" in args
        assert "https://github.com/example/picoclaw" in args

    @patch("subprocess.run")
    def test_clone_repo_failure(self, mock_run, tmp_path):
        """Repository cloning failure raises SnapshotBuildError."""
        import subprocess

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
        )

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["git", "clone"], stderr="fatal: repository not found"
        )

        with pytest.raises(SnapshotBuildError) as exc_info:
            service._clone_repo(tmp_path)

        assert "Failed to clone repository" in str(exc_info.value)
        assert exc_info.value.remediation is not None

    def test_build_image_missing_dockerfile(self, tmp_path):
        """Image build fails when Dockerfile is missing."""
        service = DaytonaSnapshotBuildService()

        with pytest.raises(SnapshotBuildError) as exc_info:
            service._build_image(tmp_path)

        assert "Dockerfile not found" in str(exc_info.value)
        assert exc_info.value.remediation is not None

    def test_build_image_success(self, tmp_path):
        """Image build succeeds with valid Dockerfile."""
        # Create a minimal Dockerfile
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM alpine:3.23\n")

        service = DaytonaSnapshotBuildService()

        with patch("src.services.daytona_snapshot_build_service.Image") as mock_image:
            mock_image.from_dockerfile.return_value = MagicMock()

            image = service._build_image(tmp_path)

            assert image is not None
            mock_image.from_dockerfile.assert_called_once_with(str(dockerfile))

    def test_build_image_prefers_picoclaw_subdir_dockerfile(self, tmp_path):
        """Image build prefers picoclaw/Dockerfile when available."""
        root_dockerfile = tmp_path / "Dockerfile"
        root_dockerfile.write_text("FROM alpine:3.23\n")

        picoclaw_dir = tmp_path / "picoclaw"
        picoclaw_dir.mkdir()
        picoclaw_dockerfile = picoclaw_dir / "Dockerfile"
        picoclaw_dockerfile.write_text("FROM alpine:3.23\n")

        service = DaytonaSnapshotBuildService()

        with patch("src.services.daytona_snapshot_build_service.Image") as mock_image:
            mock_image.from_dockerfile.return_value = MagicMock()

            service._build_image(tmp_path)

            mock_image.from_dockerfile.assert_called_once_with(str(picoclaw_dockerfile))

    def test_build_image_creates_missing_rust_toolchain_file(self, tmp_path):
        """Image build synthesizes rust-toolchain.toml when Dockerfile expects it."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "COPY Cargo.toml Cargo.lock rust-toolchain.toml ./\n",
            encoding="utf-8",
        )
        cargo_toml = tmp_path / "Cargo.toml"
        cargo_toml.write_text(
            '[package]\nname = "demo"\nversion = "0.1.0"\nrust-version = "1.91"\n',
            encoding="utf-8",
        )
        (tmp_path / "Cargo.lock").write_text("", encoding="utf-8")

        service = DaytonaSnapshotBuildService()

        with patch("src.services.daytona_snapshot_build_service.Image") as mock_image:
            mock_image.from_dockerfile.return_value = MagicMock()

            service._build_image(tmp_path)

        toolchain_file = tmp_path / "rust-toolchain.toml"
        assert toolchain_file.exists()
        assert 'channel = "1.91"' in toolchain_file.read_text(encoding="utf-8")

    def test_build_image_normalizes_buildkit_mounts(self, tmp_path):
        """Image build strips BuildKit cache mount directives when present."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \\\n+    apt-get update\n",
            encoding="utf-8",
        )

        service = DaytonaSnapshotBuildService()

        with patch("src.services.daytona_snapshot_build_service.Image") as mock_image:
            mock_image.from_dockerfile.return_value = MagicMock()

            service._build_image(tmp_path)

        normalized = dockerfile.read_text(encoding="utf-8")
        assert "--mount=type=cache" not in normalized

    def test_build_image_relocates_docker_subdir_context_for_go_repo(self, tmp_path):
        """Image build relocates docker/Dockerfile to repo root for Go COPY paths."""
        docker_dir = tmp_path / "docker"
        docker_dir.mkdir()
        dockerfile = docker_dir / "Dockerfile"
        dockerfile.write_text(
            "FROM golang:1.25-alpine\nCOPY go.mod go.sum ./\n",
            encoding="utf-8",
        )
        (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
        (tmp_path / "go.sum").write_text("", encoding="utf-8")

        service = DaytonaSnapshotBuildService()

        with patch("src.services.daytona_snapshot_build_service.Image") as mock_image:
            mock_image.from_dockerfile.return_value = MagicMock()

            service._build_image(tmp_path)

            relocated = tmp_path / ".daytona-builder.Dockerfile"
            assert relocated.exists()
            mock_image.from_dockerfile.assert_called_once_with(str(relocated))

    @pytest.mark.asyncio
    async def test_build_snapshot_success(self):
        """Full snapshot build succeeds."""
        from daytona import DaytonaError, Image

        logs = []

        def log_handler(chunk: str) -> None:
            logs.append(chunk)

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
            snapshot_name="test-snapshot",
        )

        # Create a real Image instance for the mock
        mock_image = Image.base("alpine:3.23")

        with patch.object(service, "_clone_repo"):
            with patch.object(service, "_build_image", return_value=mock_image):
                with patch(
                    "src.services.daytona_snapshot_build_service.AsyncDaytona"
                ) as mock_daytona:
                    # Mock AsyncDaytona context manager
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()
                    # Mock get to raise "not found" so it proceeds to create
                    mock_daytona_instance.snapshot.get = AsyncMock(
                        side_effect=DaytonaError("Snapshot not found")
                    )
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot(on_logs=log_handler)

        assert result.success is True
        assert result.snapshot_name == "test-snapshot"
        assert result.error_message is None
        assert result.reused is False
        assert any("Cloning" in log for log in logs)
        assert any("created successfully" in log for log in logs)
        # Verify create was called (new snapshot)
        mock_daytona_instance.snapshot.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_snapshot_missing_config(self):
        """Build fails with missing configuration."""
        service = DaytonaSnapshotBuildService(
            repo_url=None,
            snapshot_name=None,
        )

        result = await service.build_snapshot()

        assert result.success is False
        assert "Missing required configuration" in result.error_message
        assert result.remediation is not None

    @pytest.mark.asyncio
    async def test_build_snapshot_clone_failure(self):
        """Build fails when repository clone fails."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        with patch.object(
            service,
            "_clone_repo",
            side_effect=SnapshotBuildError("Clone failed"),
        ):
            result = await service.build_snapshot()

        assert result.success is False
        assert "Clone failed" in result.error_message

    @pytest.mark.asyncio
    async def test_build_snapshot_daytona_permission_error(self):
        """Build fails with permission error remediation when checking snapshot."""
        from daytona import DaytonaError

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        with patch(
            "src.services.daytona_snapshot_build_service.AsyncDaytona"
        ) as mock_daytona:
            # Mock AsyncDaytona to raise permission error on get
            mock_daytona_instance = AsyncMock()
            mock_daytona_instance.__aenter__ = AsyncMock(
                return_value=mock_daytona_instance
            )
            mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
            mock_daytona_instance.snapshot = AsyncMock()
            mock_daytona_instance.snapshot.get = AsyncMock(
                side_effect=DaytonaError("write:snapshots permission denied")
            )
            mock_daytona.return_value = mock_daytona_instance

            result = await service.build_snapshot()

        assert result.success is False
        assert "read:snapshots" in result.remediation

    @pytest.mark.asyncio
    async def test_build_snapshot_daytona_unauthorized(self):
        """Build fails with unauthorized remediation when checking snapshot."""
        from daytona import DaytonaError

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        with patch(
            "src.services.daytona_snapshot_build_service.AsyncDaytona"
        ) as mock_daytona:
            # Mock AsyncDaytona to raise unauthorized error on get
            mock_daytona_instance = AsyncMock()
            mock_daytona_instance.__aenter__ = AsyncMock(
                return_value=mock_daytona_instance
            )
            mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
            mock_daytona_instance.snapshot = AsyncMock()
            mock_daytona_instance.snapshot.get = AsyncMock(
                side_effect=DaytonaError("401 Unauthorized")
            )
            mock_daytona.return_value = mock_daytona_instance

            result = await service.build_snapshot()

        assert result.success is False
        assert "DAYTONA_API_KEY" in result.remediation

    @pytest.mark.asyncio
    async def test_build_snapshot_no_logs_callback(self):
        """Build succeeds without logs callback."""
        from daytona import DaytonaError, Image

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        # Create a real Image instance for the mock
        mock_image = Image.base("alpine:3.23")

        with patch.object(service, "_clone_repo"):
            with patch.object(service, "_build_image", return_value=mock_image):
                with patch(
                    "src.services.daytona_snapshot_build_service.AsyncDaytona"
                ) as mock_daytona:
                    # Mock AsyncDaytona context manager
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()
                    # Mock get to raise "not found" so it proceeds to create
                    mock_daytona_instance.snapshot.get = AsyncMock(
                        side_effect=DaytonaError("Snapshot not found")
                    )
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot()

        assert result.success is True
        assert result.snapshot_name == "test-snapshot"
        assert result.reused is False

    @pytest.mark.asyncio
    async def test_build_snapshot_unexpected_error(self):
        """Build handles unexpected errors gracefully."""
        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            snapshot_name="test-snapshot",
        )

        with patch.object(
            service,
            "_validate_config",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await service.build_snapshot()

        assert result.success is False
        assert "Unexpected error" in result.error_message

    @pytest.mark.asyncio
    async def test_build_snapshot_reuses_when_exists(self):
        """Snapshot build reuses existing snapshot when it already exists."""
        from daytona import Image

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
            snapshot_name="existing-snapshot",
        )

        with patch(
            "src.services.daytona_snapshot_build_service.AsyncDaytona"
        ) as mock_daytona:
            # Mock AsyncDaytona - snapshot exists
            mock_daytona_instance = AsyncMock()
            mock_daytona_instance.__aenter__ = AsyncMock(
                return_value=mock_daytona_instance
            )
            mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
            mock_daytona_instance.snapshot = AsyncMock()
            # Mock get to succeed (snapshot exists)
            mock_snapshot = MagicMock()
            mock_snapshot.name = "existing-snapshot"
            mock_snapshot.state = "active"
            mock_daytona_instance.snapshot.get = AsyncMock(return_value=mock_snapshot)
            mock_daytona_instance.snapshot.create = AsyncMock()
            mock_daytona.return_value = mock_daytona_instance

            result = await service.build_snapshot()

        # Verify result indicates success and reuse
        assert result.success is True
        assert result.snapshot_name == "existing-snapshot"
        assert result.reused is True
        assert result.error_message is None

        # Verify snapshot.create was NOT called (idempotent behavior)
        mock_daytona_instance.snapshot.create.assert_not_called()
        # Verify snapshot.get was called with correct name
        mock_daytona_instance.snapshot.get.assert_called_once_with("existing-snapshot")

    @pytest.mark.asyncio
    async def test_build_snapshot_recreates_when_existing_is_error(self):
        """Snapshot build deletes errored snapshot and recreates it."""
        from daytona import DaytonaError, Image

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
            snapshot_name="errored-snapshot",
        )

        mock_image = Image.base("alpine:3.23")

        with patch.object(service, "_clone_repo"):
            with patch.object(service, "_build_image", return_value=mock_image):
                with patch(
                    "src.services.daytona_snapshot_build_service.AsyncDaytona"
                ) as mock_daytona:
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()

                    mock_snapshot = MagicMock()
                    mock_snapshot.name = "errored-snapshot"
                    mock_snapshot.state = "error"

                    mock_daytona_instance.snapshot.get = AsyncMock(
                        return_value=mock_snapshot
                    )
                    mock_daytona_instance.snapshot.delete = AsyncMock()
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot()

        assert result.success is True
        assert result.reused is False
        mock_daytona_instance.snapshot.delete.assert_called_once_with(mock_snapshot)
        mock_daytona_instance.snapshot.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_snapshot_creates_when_missing(self):
        """Snapshot build creates new snapshot when it doesn't exist."""
        from daytona import DaytonaError, Image

        logs = []

        def log_handler(chunk: str) -> None:
            logs.append(chunk)

        service = DaytonaSnapshotBuildService(
            repo_url="https://github.com/example/picoclaw",
            repo_ref="main",
            snapshot_name="new-snapshot",
        )

        # Create a real Image instance for the mock
        mock_image = Image.base("alpine:3.23")

        with patch.object(service, "_clone_repo"):
            with patch.object(service, "_build_image", return_value=mock_image):
                with patch(
                    "src.services.daytona_snapshot_build_service.AsyncDaytona"
                ) as mock_daytona:
                    # Mock AsyncDaytona - snapshot does not exist
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()
                    # Mock get to raise "not found" error
                    mock_daytona_instance.snapshot.get = AsyncMock(
                        side_effect=DaytonaError("Snapshot not found: new-snapshot")
                    )
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot(on_logs=log_handler)

        # Verify result indicates success and NOT reused
        assert result.success is True
        assert result.snapshot_name == "new-snapshot"
        assert result.reused is False
        assert result.error_message is None

        # Verify snapshot.create was called (new snapshot created)
        mock_daytona_instance.snapshot.create.assert_called_once()
        # Verify snapshot.get was called with correct name
        mock_daytona_instance.snapshot.get.assert_called_once_with("new-snapshot")
        # Verify appropriate log message
        assert any("not found" in log.lower() for log in logs)
