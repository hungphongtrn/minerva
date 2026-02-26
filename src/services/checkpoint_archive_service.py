"""Checkpoint archive service for packaging and unpacking checkpoint data."""

from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import zstandard

from src.infrastructure.checkpoints.s3_checkpoint_store import (
    CheckpointManifest,
)

if TYPE_CHECKING:
    from src.infrastructure.checkpoints.s3_checkpoint_store import (
        S3CheckpointStore,
    )


@dataclass(frozen=True)
class CheckpointArchiveResult:
    """Result of creating a checkpoint archive.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        archive_bytes: Compressed archive bytes (zstd compressed tar)
        manifest: Checkpoint manifest with checksum and metadata
    """

    checkpoint_id: UUID
    archive_bytes: bytes
    manifest: "CheckpointManifest"


@dataclass
class SessionState:
    """Runtime session state to be checkpointed.

    Captures only dynamic memory/session state, excluding static identity files.

    Attributes:
        session_data: Key-value session storage
        conversation_history: List of conversation turns
        runtime_variables: Environment and context variables
        metadata: Additional checkpoint metadata
    """

    session_data: dict[str, Any] = field(default_factory=dict)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    runtime_variables: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert session state to dictionary."""
        return {
            "session_data": self.session_data,
            "conversation_history": self.conversation_history,
            "runtime_variables": self.runtime_variables,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        """Create session state from dictionary."""
        return cls(
            session_data=data.get("session_data", {}),
            conversation_history=data.get("conversation_history", []),
            runtime_variables=data.get("runtime_variables", {}),
            metadata=data.get("metadata", {}),
        )


class CheckpointArchiveService:
    """Service for creating and extracting checkpoint archives.

    Checkpoint Scope Rules:
    - INCLUDES: Dynamic session state, conversation history, runtime variables
    - EXCLUDES: Static identity files (AGENT.md, SOUL.md, IDENTITY.md, skills/)

    Archive Format:
    - Compression: zstandard (zstd) for speed/ratio balance
    - Container: tar for structured file storage
    - Layout:
        checkpoint.json       # Session state and metadata
        checksum.sha256       # SHA-256 of uncompressed bytes
    """

    # Files/directories that must never be included in checkpoints
    EXCLUDED_PATHS = {
        "AGENT.md",
        "SOUL.md",
        "IDENTITY.md",
        "skills",
        ".skills",
        ".git",
        ".gitignore",
        ".env",
        ".env.local",
    }

    # Checkpoint format version for migration handling
    CHECKPOINT_VERSION = "1.0.0"

    def __init__(self, store: S3CheckpointStore | None = None):
        """Initialize archive service.

        Args:
            store: Optional S3 checkpoint store for persistence operations
        """
        self._store = store

    def create_checkpoint(
        self,
        workspace_id: UUID,
        agent_pack_id: UUID,
        session_state: SessionState,
        checkpoint_id: UUID | None = None,
    ) -> CheckpointArchiveResult:
        """Create a checkpoint archive from session state.

        Packages only dynamic runtime state. Computes SHA-256 checksum
        on the final archive bytes for integrity verification.

        Args:
            workspace_id: Workspace UUID
            agent_pack_id: Agent pack UUID
            session_state: Runtime session state to checkpoint
            checkpoint_id: Optional specific checkpoint ID (generated if not provided)

        Returns:
            CheckpointArchiveResult with archive bytes and manifest
        """
        checkpoint_id = checkpoint_id or uuid4()

        # Build archive content
        archive_bytes = self._pack_archive(session_state, checkpoint_id)

        # Compute checksum on compressed bytes
        checksum = hashlib.sha256(archive_bytes).hexdigest()

        # Create manifest
        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            archive_checksum=checksum,
            archive_size_bytes=len(archive_bytes),
            content_version=self.CHECKPOINT_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "session_keys": list(session_state.session_data.keys()),
                "conversation_turns": len(session_state.conversation_history),
                "runtime_var_count": len(session_state.runtime_variables),
            },
        )

        return CheckpointArchiveResult(
            checkpoint_id=checkpoint_id,
            archive_bytes=archive_bytes,
            manifest=manifest,
        )

    def _pack_archive(
        self,
        session_state: SessionState,
        checkpoint_id: UUID,
    ) -> bytes:
        """Pack session state into compressed archive bytes.

        Creates a tar archive with checkpoint.json and checksum.sha256,
        then compresses with zstandard.

        Args:
            session_state: Session state to pack
            checkpoint_id: Checkpoint identifier

        Returns:
            zstd-compressed archive bytes
        """
        # Create in-memory tar archive
        tar_buffer = BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            # Add checkpoint.json with session state
            state_json = json.dumps(session_state.to_dict(), indent=2, default=str)
            state_bytes = state_json.encode("utf-8")

            state_info = tarfile.TarInfo(name="checkpoint.json")
            state_info.size = len(state_bytes)
            tar.addfile(state_info, BytesIO(state_bytes))

            # Add checksum.sha256 placeholder (will be filled after compression)
            # Note: Actual checksum is computed on compressed bytes, not tar contents
            checksum_placeholder = b"SHA256_OF_COMPRESSED_ARCHIVE\n"
            checksum_info = tarfile.TarInfo(name="checksum.sha256")
            checksum_info.size = len(checksum_placeholder)
            tar.addfile(checksum_info, BytesIO(checksum_placeholder))

            # Add checkpoint metadata
            meta = {
                "checkpoint_id": str(checkpoint_id),
                "version": self.CHECKPOINT_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "scope": "memory_session_only",
                "excluded": list(self.EXCLUDED_PATHS),
            }
            meta_json = json.dumps(meta, indent=2)
            meta_bytes = meta_json.encode("utf-8")

            meta_info = tarfile.TarInfo(name="checkpoint.meta.json")
            meta_info.size = len(meta_bytes)
            tar.addfile(meta_info, BytesIO(meta_bytes))

        # Compress with zstandard
        tar_bytes = tar_buffer.getvalue()
        compressor = zstandard.ZstdCompressor(level=3)  # Balance speed/ratio
        compressed_bytes = compressor.compress(tar_bytes)

        return compressed_bytes

    def extract_checkpoint(
        self,
        archive_bytes: bytes,
        expected_checksum: str | None = None,
    ) -> SessionState:
        """Extract session state from checkpoint archive.

        Validates checksum if provided, then decompresses and unpacks
        the session state.

        Args:
            archive_bytes: Compressed checkpoint archive
            expected_checksum: Optional checksum to validate against

        Returns:
            Extracted SessionState

        Raises:
            ChecksumMismatchError: If checksum validation fails
            ArchiveCorruptedError: If archive is corrupted or unreadable
        """
        # Validate checksum if provided
        if expected_checksum:
            actual_checksum = hashlib.sha256(archive_bytes).hexdigest()
            if actual_checksum != expected_checksum:
                raise ChecksumMismatchError(
                    f"Checksum mismatch: expected {expected_checksum[:16]}..., "
                    f"got {actual_checksum[:16]}..."
                )

        try:
            # Decompress
            decompressor = zstandard.ZstdDecompressor()
            tar_bytes = decompressor.decompress(archive_bytes)

            # Extract tar
            tar_buffer = BytesIO(tar_bytes)
            with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
                # Read checkpoint.json
                state_member = tar.getmember("checkpoint.json")
                state_file = tar.extractfile(state_member)
                if state_file is None:
                    raise ArchiveCorruptedError("checkpoint.json not found in archive")

                state_data = json.loads(state_file.read().decode("utf-8"))
                return SessionState.from_dict(state_data)

        except zstandard.ZstdError as e:
            raise ArchiveCorruptedError(f"Failed to decompress archive: {e}") from e
        except (tarfile.TarError, KeyError, json.JSONDecodeError) as e:
            raise ArchiveCorruptedError(f"Failed to unpack archive: {e}") from e

    def save_checkpoint(
        self,
        workspace_id: UUID,
        agent_pack_id: UUID,
        session_state: SessionState,
        checkpoint_id: UUID | None = None,
    ) -> CheckpointArchiveResult:
        """Create and persist a checkpoint to S3 storage.

        Convenience method that creates the archive and immediately
        persists it to the configured S3 store.

        Args:
            workspace_id: Workspace UUID
            agent_pack_id: Agent pack UUID
            session_state: Runtime session state to checkpoint
            checkpoint_id: Optional specific checkpoint ID

        Returns:
            CheckpointArchiveResult with archive and manifest

        Raises:
            StorageError: If S3 store is not configured or write fails
        """
        if self._store is None:
            raise StorageError("S3CheckpointStore not configured")

        result = self.create_checkpoint(
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            session_state=session_state,
            checkpoint_id=checkpoint_id,
        )

        self._store.put_archive(
            workspace_id=workspace_id,
            checkpoint_id=result.checkpoint_id,
            archive_bytes=result.archive_bytes,
            manifest=result.manifest,
        )

        return result

    def load_checkpoint(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
    ) -> SessionState:
        """Load and extract a checkpoint from S3 storage.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID

        Returns:
            Extracted SessionState

        Raises:
            StorageError: If S3 store is not configured
            CheckpointNotFoundError: If checkpoint doesn't exist
        """
        if self._store is None:
            raise StorageError("S3CheckpointStore not configured")

        # Get manifest first for checksum validation
        manifest = self._store.get_manifest(workspace_id, checkpoint_id)

        # Get archive bytes
        archive_bytes = self._store.get_archive(workspace_id, checkpoint_id)

        # Extract with checksum validation
        return self.extract_checkpoint(
            archive_bytes,
            expected_checksum=manifest.archive_checksum,
        )

    @staticmethod
    def should_exclude_path(path: str | Path) -> bool:
        """Check if a path should be excluded from checkpoint.

        Static identity files and sensitive paths are excluded.

        Args:
            path: Path to check

        Returns:
            True if path should be excluded
        """
        path_str = str(path)
        path_name = Path(path_str).name

        # Check exact filename matches
        if path_name in CheckpointArchiveService.EXCLUDED_PATHS:
            return True

        # Check if any component is excluded
        for part in Path(path_str).parts:
            if part in CheckpointArchiveService.EXCLUDED_PATHS:
                return True

        return False


class ChecksumMismatchError(Exception):
    """Raised when checkpoint checksum validation fails."""

    pass


class ArchiveCorruptedError(Exception):
    """Raised when checkpoint archive is corrupted or unreadable."""

    pass


class StorageError(Exception):
    """Raised when checkpoint storage operation fails."""

    pass


class CheckpointNotFoundError(Exception):
    """Raised when checkpoint is not found."""

    pass
