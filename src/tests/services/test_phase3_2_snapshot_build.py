"""Tests for Daytona snapshot build service.

Tests cover:
- Configuration validation
- Repository cloning
- Image building from Dockerfile
- Snapshot creation via Daytona SDK
- Error handling and remediation
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

    @pytest.mark.asyncio
    async def test_build_snapshot_success(self):
        """Full snapshot build succeeds."""
        from daytona import Image

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
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot(on_logs=log_handler)

        assert result.success is True
        assert result.snapshot_name == "test-snapshot"
        assert result.error_message is None
        assert any("Cloning" in log for log in logs)
        assert any("created successfully" in log for log in logs)

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
        """Build fails with permission error remediation."""
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
                    # Mock AsyncDaytona to raise permission error
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()
                    mock_daytona_instance.snapshot.create = AsyncMock(
                        side_effect=DaytonaError("write:snapshots permission denied")
                    )
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot()

        assert result.success is False
        assert "write:snapshots" in result.remediation

    @pytest.mark.asyncio
    async def test_build_snapshot_daytona_unauthorized(self):
        """Build fails with unauthorized remediation."""
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
                    # Mock AsyncDaytona to raise unauthorized error
                    mock_daytona_instance = AsyncMock()
                    mock_daytona_instance.__aenter__ = AsyncMock(
                        return_value=mock_daytona_instance
                    )
                    mock_daytona_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_daytona_instance.snapshot = AsyncMock()
                    mock_daytona_instance.snapshot.create = AsyncMock(
                        side_effect=DaytonaError("401 Unauthorized")
                    )
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot()

        assert result.success is False
        assert "DAYTONA_API_KEY" in result.remediation

    @pytest.mark.asyncio
    async def test_build_snapshot_no_logs_callback(self):
        """Build succeeds without logs callback."""
        from daytona import Image

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
                    mock_daytona_instance.snapshot.create = AsyncMock()
                    mock_daytona.return_value = mock_daytona_instance

                    result = await service.build_snapshot()

        assert result.success is True
        assert result.snapshot_name == "test-snapshot"

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
