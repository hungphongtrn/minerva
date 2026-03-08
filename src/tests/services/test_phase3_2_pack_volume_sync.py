"""Tests for Daytona pack volume sync service.

Tests verify:
- Deterministic volume naming (agent-pack-{id}-{digest})
- File upload destinations under /workspace/pack/
- Cleanup runs even on upload errors
- Only static identity files are synced (no runtime config/secrets)
"""

import os
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from daytona import VolumeMount, FileUpload

from src.services.daytona_pack_volume_service import (
    DaytonaPackVolumeService,
    PackSyncError,
)


@pytest.fixture
def pack_id():
    """Generate a test pack ID."""
    return uuid4()


@pytest.fixture
def source_digest():
    """Generate a test source digest."""
    return "a" * 64  # SHA-256 is 64 hex chars


@pytest.fixture
def pack_files(tmp_path):
    """Create a minimal valid pack structure."""
    # Create required files
    (tmp_path / "AGENT.md").write_text("# Agent\n")
    (tmp_path / "SOUL.md").write_text("# Soul\n")
    (tmp_path / "IDENTITY.md").write_text("# Identity\n")

    # Create skills directory with a skill file
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "test_skill.md").write_text("# Test Skill\n")

    return tmp_path


class TestVolumeNaming:
    """Tests for deterministic volume naming."""

    def test_volume_name_format(self, pack_id, source_digest):
        """Volume name follows agent-pack-{id}-{digest} pattern with full UUID and digest."""
        service = DaytonaPackVolumeService()
        volume_name = service._compute_volume_name(pack_id, source_digest)

        # Should match pattern: agent-pack-{full UUID}-{full digest} (no truncation)
        expected_name = f"agent-pack-{pack_id}-{source_digest}"
        assert volume_name == expected_name

    def test_volume_name_deterministic(self, pack_id, source_digest):
        """Same pack+digest always produces same volume name."""
        service = DaytonaPackVolumeService()

        name1 = service._compute_volume_name(pack_id, source_digest)
        name2 = service._compute_volume_name(pack_id, source_digest)

        assert name1 == name2

    def test_volume_name_different_digests(self, pack_id):
        """Different digests produce different volume names."""
        service = DaytonaPackVolumeService()

        digest1 = "a" * 64
        digest2 = "b" * 64

        name1 = service._compute_volume_name(pack_id, digest1)
        name2 = service._compute_volume_name(pack_id, digest2)

        assert name1 != name2


class TestPackFileCollection:
    """Tests for pack file collection."""

    def test_collect_required_files(self, pack_files):
        """Collects AGENT.md, SOUL.md, IDENTITY.md, and skills/**."""
        service = DaytonaPackVolumeService()
        files = service._collect_pack_files(str(pack_files))

        # Should have 4 files: 3 required + 1 skill
        assert len(files) == 4
        assert "AGENT.md" in files
        assert "SOUL.md" in files
        assert "IDENTITY.md" in files
        assert "skills/test_skill.md" in files

    def test_collect_excludes_other_files(self, pack_files):
        """Does NOT collect config.json or other files."""
        # Add files that should be excluded
        (pack_files / "config.json").write_text('{"key": "value"}')
        (pack_files / "README.md").write_text("# README")
        (pack_files / ".env").write_text("SECRET=value")

        service = DaytonaPackVolumeService()
        files = service._collect_pack_files(str(pack_files))

        # Should still only have pack files
        assert "config.json" not in files
        assert "README.md" not in files
        assert ".env" not in files

    def test_collect_missing_required_file(self, pack_files):
        """Raises PackSyncError if required file is missing."""
        # Remove a required file
        (pack_files / "AGENT.md").unlink()

        service = DaytonaPackVolumeService()

        with pytest.raises(PackSyncError) as exc_info:
            service._collect_pack_files(str(pack_files))

        assert "Required pack file missing" in str(exc_info.value)
        assert "AGENT.md" in str(exc_info.value)

    def test_collect_missing_skills_directory(self, pack_files):
        """Raises PackSyncError if skills/ directory is missing."""
        # Remove skills directory
        import shutil

        shutil.rmtree(pack_files / "skills")

        service = DaytonaPackVolumeService()

        with pytest.raises(PackSyncError) as exc_info:
            service._collect_pack_files(str(pack_files))

        assert "Required pack directory missing" in str(exc_info.value)
        assert "skills" in str(exc_info.value)

    def test_collect_invalid_source_path(self):
        """Raises PackSyncError if source path doesn't exist."""
        service = DaytonaPackVolumeService()

        with pytest.raises(PackSyncError) as exc_info:
            service._collect_pack_files("/nonexistent/path")

        assert "does not exist" in str(exc_info.value)

    def test_collect_nested_skills(self, pack_files):
        """Collects files in nested skill directories."""
        # Create nested structure
        nested_skill = pack_files / "skills" / "category1" / "skill1.md"
        nested_skill.parent.mkdir(parents=True)
        nested_skill.write_text("# Nested Skill\n")

        service = DaytonaPackVolumeService()
        files = service._collect_pack_files(str(pack_files))

        assert "skills/category1/skill1.md" in files


class TestSyncPackToVolume:
    """Tests for pack volume sync."""

    @pytest.mark.asyncio
    async def test_sync_creates_volume(self, pack_id, source_digest, pack_files):
        """Ensures volume is created via Daytona API."""
        service = DaytonaPackVolumeService()

        mock_volume = MagicMock()
        mock_volume.name = f"agent-pack-{pack_id}-{source_digest}"

        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-123"
        mock_sandbox.fs.upload_files = AsyncMock()

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            mock_daytona_cls.return_value = mock_daytona

            volume_name = await service.sync_pack_to_volume(
                pack_id=pack_id,
                source_path=str(pack_files),
                source_digest=source_digest,
            )

            # Verify volume was created/retrieved
            mock_daytona.volume.get.assert_called()

            # Verify volume name is correct (full UUID + full digest, no truncation)
            expected_name = f"agent-pack-{pack_id}-{source_digest}"
            assert volume_name == expected_name

    @pytest.mark.asyncio
    async def test_sync_uploads_to_correct_destination(self, pack_id, source_digest, pack_files):
        """Files are uploaded to /workspace/pack (volume mount point)."""
        service = DaytonaPackVolumeService()

        mock_volume = MagicMock()
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.fs.upload_files = AsyncMock()

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            mock_daytona_cls.return_value = mock_daytona

            await service.sync_pack_to_volume(
                pack_id=pack_id,
                source_path=str(pack_files),
                source_digest=source_digest,
            )

            # Verify upload was called with FileUpload list (SDK-correct primitive)
            mock_sandbox.fs.upload_files.assert_called_once()
            call_args = mock_sandbox.fs.upload_files.call_args[0]

            # First positional argument should be a list of FileUpload objects
            file_uploads = (
                call_args[0]
                if call_args
                else mock_sandbox.fs.upload_files.call_args[1].get("files", [])
            )
            assert len(file_uploads) == 4  # 3 required files + 1 skill file

            # All uploads should be FileUpload objects with correct destinations under /workspace/pack
            for upload in file_uploads:
                assert isinstance(upload, FileUpload)
                assert upload.destination.startswith("/workspace/pack/")

    @pytest.mark.asyncio
    async def test_sync_cleanup_on_upload_error(self, pack_id, source_digest, pack_files):
        """Disposable sandbox is cleaned up even if upload fails."""
        service = DaytonaPackVolumeService()

        mock_volume = MagicMock()
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.fs.upload_files = AsyncMock(side_effect=Exception("Upload failed"))

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            mock_daytona_cls.return_value = mock_daytona

            # Should raise PackSyncError
            with pytest.raises(PackSyncError):
                await service.sync_pack_to_volume(
                    pack_id=pack_id,
                    source_path=str(pack_files),
                    source_digest=source_digest,
                )

            # Verify cleanup was attempted (called twice: once for error, once in finally)
            # The important thing is that delete was called
            assert mock_daytona.delete.called

    @pytest.mark.asyncio
    async def test_sync_creates_sandbox_with_volume_mount(
        self, pack_id, source_digest, pack_files
    ):
        """Disposable sandbox is created with volume mounted at /workspace/pack using SDK types."""
        service = DaytonaPackVolumeService()

        # Full UUID + full digest volume name (no truncation)
        expected_volume_name = f"agent-pack-{pack_id}-{source_digest}"

        mock_volume = MagicMock()
        mock_volume.name = expected_volume_name

        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.fs.upload_files = AsyncMock()

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)
            mock_daytona.delete = AsyncMock()

            mock_daytona_cls.return_value = mock_daytona

            await service.sync_pack_to_volume(
                pack_id=pack_id,
                source_path=str(pack_files),
                source_digest=source_digest,
            )

            # Verify sandbox was created with CreateSandboxFromSnapshotParams
            mock_daytona.create.assert_called_once()
            call_args = mock_daytona.create.call_args[0]

            # First positional arg should be CreateSandboxFromSnapshotParams
            params = call_args[0]
            assert hasattr(params, "volumes")
            assert len(params.volumes) == 1

            volume_mount = params.volumes[0]
            assert volume_mount.volume_id == expected_volume_name
            assert volume_mount.mount_path == "/workspace/pack"

    @pytest.mark.asyncio
    async def test_sync_cleanup_on_volume_error(self, pack_id, source_digest, pack_files):
        """Handles volume creation errors gracefully."""
        service = DaytonaPackVolumeService()

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)

            # Simulate volume creation failure
            from daytona import DaytonaError

            mock_daytona.volume.get = AsyncMock(side_effect=DaytonaError("Volume creation failed"))

            mock_daytona_cls.return_value = mock_daytona

            with pytest.raises(PackSyncError) as exc_info:
                await service.sync_pack_to_volume(
                    pack_id=pack_id,
                    source_path=str(pack_files),
                    source_digest=source_digest,
                )

            assert "Failed to create/get volume" in str(exc_info.value)


class TestEnsureVolumeExists:
    """Tests for volume existence check."""

    @pytest.mark.asyncio
    async def test_ensure_creates_volume(self, pack_id, source_digest):
        """Creates volume if it doesn't exist."""
        service = DaytonaPackVolumeService()

        # Full UUID + full digest volume name (no truncation)
        expected_volume_name = f"agent-pack-{pack_id}-{source_digest}"
        mock_volume = MagicMock()
        mock_volume.name = expected_volume_name

        with patch("src.services.daytona_pack_volume_service.AsyncDaytona") as mock_daytona_cls:
            mock_daytona = AsyncMock()
            mock_daytona.__aenter__ = AsyncMock(return_value=mock_daytona)
            mock_daytona.__aexit__ = AsyncMock(return_value=None)
            mock_daytona.volume.get = AsyncMock(return_value=mock_volume)

            mock_daytona_cls.return_value = mock_daytona

            volume_name = await service.ensure_volume_exists(
                pack_id=pack_id,
                source_digest=source_digest,
            )

            # Verify volume.get was called with create=True
            mock_daytona.volume.get.assert_called_once_with(
                expected_volume_name,
                create=True,
            )

            assert volume_name == expected_volume_name
