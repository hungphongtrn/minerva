"""Daytona pack volume sync service.

Implements volume-per-digest pack sync using disposable sandboxes.
Ensures agent pack files are stored in immutable, digest-named volumes.

Key features:
- Deterministic volume naming: agent-pack-{pack_id}-{digest}
- Disposable sandbox for file upload (cleaned up after sync)
- Cleanup guaranteed even on upload errors
- Only syncs AGENT.md, SOUL.md, IDENTITY.md, skills/** (no runtime config/secrets)
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID

from daytona import (
    AsyncDaytona,
    DaytonaConfig,
    DaytonaError,
    CreateSandboxFromSnapshotParams,
    VolumeMount,
    FileUpload,
)

from src.infrastructure.sandbox.providers.base import (
    SandboxProviderError,
    SandboxConfigurationError,
)


class PackSyncError(SandboxProviderError):
    """Raised when pack volume sync fails."""

    def __init__(
        self,
        message: str,
        pack_id: Optional[UUID] = None,
        volume_name: Optional[str] = None,
    ):
        super().__init__(message, provider_ref=volume_name)
        self.pack_id = pack_id
        self.volume_name = volume_name


class DaytonaPackVolumeService:
    """Service for syncing agent packs to Daytona Volumes.

    Uses disposable sandboxes to upload pack files into digest-pinned volumes.
    Each pack+digest combination gets its own immutable volume.

    Volume naming contract: agent-pack-{pack_id}-{source_digest}
    - Deterministic: same pack+digest always maps to same volume
    - Immutable: digest changes create new volume (old volume remains for running sandboxes)
    - Shared: multiple sandboxes can mount the same volume (read-only)
    """

    # Pack files to sync (static identity files only)
    PACK_FILES = ["AGENT.md", "SOUL.md", "IDENTITY.md"]
    PACK_DIRS = ["skills"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        target: str = "us",
        snapshot_name: Optional[str] = None,
    ):
        """Initialize pack volume service.

        Args:
            api_key: Daytona API key (defaults to DAYTONA_API_KEY env var)
            api_url: Daytona API URL (defaults to DAYTONA_API_URL env var)
            target: Target region for Daytona Cloud
            snapshot_name: Picoclaw snapshot name for disposable sandboxes
        """
        self._api_key = api_key or os.environ.get("DAYTONA_API_KEY", "")
        self._api_url = api_url or os.environ.get("DAYTONA_API_URL", "")
        self._target = target
        self._snapshot_name = snapshot_name or os.environ.get(
            "DAYTONA_PICOCLAW_SNAPSHOT_NAME", "picoclaw-snapshot"
        )

    def _create_config(self) -> DaytonaConfig:
        """Create DaytonaConfig from resolved settings."""
        config_kwargs: Dict[str, Any] = {"target": self._target}

        if self._api_key:
            config_kwargs["api_key"] = self._api_key
        if self._api_url:
            config_kwargs["api_url"] = self._api_url

        return DaytonaConfig(**config_kwargs)

    def _compute_volume_name(self, pack_id: UUID, source_digest: str) -> str:
        """Compute deterministic volume name from pack ID and digest.

        Args:
            pack_id: Agent pack UUID
            source_digest: SHA-256 digest of pack content

        Returns:
            Volume name: agent-pack-{pack_id}-{source_digest}
            (full UUID + full digest, no truncation)
        """
        return f"agent-pack-{pack_id}-{source_digest}"

    def _collect_pack_files(self, source_path: str) -> Dict[str, bytes]:
        """Collect pack files for upload.

        Walks the source directory and collects only the files that should
        be synced to the volume (AGENT.md, SOUL.md, IDENTITY.md, skills/**).

        Args:
            source_path: Path to pack directory

        Returns:
            Dict mapping relative paths to file contents

        Raises:
            PackSyncError: If source path is invalid or files are missing
        """
        path = Path(source_path)

        if not path.exists():
            raise PackSyncError(
                f"Pack source path does not exist: {source_path}",
                pack_id=None,
            )

        if not path.is_dir():
            raise PackSyncError(
                f"Pack source path is not a directory: {source_path}",
                pack_id=None,
            )

        files_to_upload: Dict[str, bytes] = {}

        # Collect required files
        for file_name in self.PACK_FILES:
            file_path = path / file_name
            if not file_path.exists():
                raise PackSyncError(
                    f"Required pack file missing: {file_name}",
                    pack_id=None,
                )

            try:
                with open(file_path, "rb") as f:
                    files_to_upload[file_name] = f.read()
            except (OSError, IOError) as e:
                raise PackSyncError(
                    f"Failed to read pack file {file_name}: {e}",
                    pack_id=None,
                )

        # Collect skills directory
        skills_path = path / "skills"
        if not skills_path.exists() or not skills_path.is_dir():
            raise PackSyncError(
                "Required pack directory missing: skills/",
                pack_id=None,
            )

        # Walk skills directory recursively
        for root, dirs, files in os.walk(skills_path):
            # Sort for deterministic ordering
            dirs.sort()
            for file_name in sorted(files):
                file_path = Path(root) / file_name
                rel_path = file_path.relative_to(path)

                try:
                    with open(file_path, "rb") as f:
                        files_to_upload[str(rel_path)] = f.read()
                except (OSError, IOError) as e:
                    raise PackSyncError(
                        f"Failed to read pack file {rel_path}: {e}",
                        pack_id=None,
                    )

        return files_to_upload

    async def sync_pack_to_volume(
        self,
        pack_id: UUID,
        source_path: str,
        source_digest: str,
    ) -> str:
        """Sync agent pack files to a digest-pinned Daytona Volume.

        Creates or reuses a volume named agent-pack-{pack_id}-{digest},
        then uses a disposable sandbox to upload pack files into it.

        Args:
            pack_id: Agent pack UUID
            source_path: Local filesystem path to pack directory
            source_digest: SHA-256 digest of pack content

        Returns:
            Volume name that was synced

        Raises:
            PackSyncError: If sync fails
        """
        # Compute deterministic volume name
        volume_name = self._compute_volume_name(pack_id, source_digest)

        # Collect files to upload
        try:
            files_to_upload = self._collect_pack_files(source_path)
        except PackSyncError:
            raise
        except Exception as e:
            raise PackSyncError(
                f"Failed to collect pack files: {e}",
                pack_id=pack_id,
                volume_name=volume_name,
            )

        # Upload via disposable sandbox
        sandbox_id = None

        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                # Ensure volume exists (create if needed)
                try:
                    volume = await daytona.volume.get(volume_name, create=True)
                except DaytonaError as e:
                    raise PackSyncError(
                        f"Failed to create/get volume {volume_name}: {e}",
                        pack_id=pack_id,
                        volume_name=volume_name,
                    )

                # Create disposable sandbox from snapshot with volume mounted
                try:
                    # Build sandbox params with volume mount using SDK types
                    sandbox_params = CreateSandboxFromSnapshotParams(
                        snapshot=self._snapshot_name,
                        volumes=[
                            VolumeMount(
                                volume_id=volume_name,
                                mount_path="/workspace/pack",
                            )
                        ],
                        timeout=60,
                    )

                    sandbox = await daytona.create(sandbox_params)
                    sandbox_id = sandbox.id if hasattr(sandbox, "id") else "unknown"

                except DaytonaError as e:
                    raise PackSyncError(
                        f"Failed to create disposable sandbox: {e}",
                        pack_id=pack_id,
                        volume_name=volume_name,
                    )

                # Upload files into mounted volume
                try:
                    # Convert files to FileUpload objects for SDK upload
                    # Files are uploaded to /workspace/pack/ which is the volume mount point
                    file_uploads = [
                        FileUpload(
                            source=content,
                            destination=f"/workspace/pack/{rel_path}",
                        )
                        for rel_path, content in files_to_upload.items()
                    ]

                    await sandbox.fs.upload_files(file_uploads)

                except DaytonaError as e:
                    raise PackSyncError(
                        f"Failed to upload pack files to volume: {e}",
                        pack_id=pack_id,
                        volume_name=volume_name,
                    )
                except Exception as e:
                    raise PackSyncError(
                        f"Unexpected error uploading files: {e}",
                        pack_id=pack_id,
                        volume_name=volume_name,
                    )

                return volume_name

        except PackSyncError:
            raise
        except Exception as e:
            raise PackSyncError(
                f"Unexpected error during pack sync: {e}",
                pack_id=pack_id,
                volume_name=volume_name,
            )
        finally:
            # Cleanup: delete disposable sandbox
            if sandbox_id:
                try:
                    config = self._create_config()
                    async with AsyncDaytona(config=config) as daytona:
                        try:
                            sandbox = await daytona.get(sandbox_id)
                            await daytona.delete(sandbox, timeout=30)
                        except (DaytonaError, Exception):
                            # Best-effort cleanup - don't fail on cleanup errors
                            pass
                except Exception:
                    # Don't fail on cleanup errors
                    pass

    async def ensure_volume_exists(
        self,
        pack_id: UUID,
        source_digest: str,
    ) -> str:
        """Ensure a volume exists for the given pack+digest combination.

        Does NOT upload files - just ensures the volume is created.

        Args:
            pack_id: Agent pack UUID
            source_digest: SHA-256 digest of pack content

        Returns:
            Volume name

        Raises:
            PackSyncError: If volume creation fails
        """
        volume_name = self._compute_volume_name(pack_id, source_digest)

        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                await daytona.volume.get(volume_name, create=True)
                return volume_name
        except DaytonaError as e:
            raise PackSyncError(
                f"Failed to ensure volume {volume_name} exists: {e}",
                pack_id=pack_id,
                volume_name=volume_name,
            )
