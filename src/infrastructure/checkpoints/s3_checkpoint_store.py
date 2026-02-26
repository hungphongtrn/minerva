"""S3-compatible checkpoint storage implementation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True)
class CheckpointManifest:
    """Metadata describing a checkpoint archive.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint
        workspace_id: Workspace this checkpoint belongs to
        agent_pack_id: Agent pack this checkpoint is for
        archive_checksum: SHA-256 checksum of the archive bytes
        archive_size_bytes: Size of the compressed archive
        content_version: Checkpoint format version
        created_at: ISO 8601 timestamp when checkpoint was created
        metadata: Optional additional metadata (session state keys, etc.)
    """

    checkpoint_id: UUID
    workspace_id: UUID
    agent_pack_id: UUID
    archive_checksum: str
    archive_size_bytes: int
    content_version: str = "1.0.0"
    created_at: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary for serialization."""
        return {
            "checkpoint_id": str(self.checkpoint_id),
            "workspace_id": str(self.workspace_id),
            "agent_pack_id": str(self.agent_pack_id),
            "archive_checksum": self.archive_checksum,
            "archive_size_bytes": self.archive_size_bytes,
            "content_version": self.content_version,
            "created_at": self.created_at,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointManifest:
        """Create manifest from dictionary."""
        return cls(
            checkpoint_id=UUID(data["checkpoint_id"]),
            workspace_id=UUID(data["workspace_id"]),
            agent_pack_id=UUID(data["agent_pack_id"]),
            archive_checksum=data["archive_checksum"],
            archive_size_bytes=data["archive_size_bytes"],
            content_version=data.get("content_version", "1.0.0"),
            created_at=data.get("created_at"),
            metadata=data.get("metadata"),
        )


class S3CheckpointStore:
    """S3-compatible storage for checkpoint archives and manifests.

    Implements deterministic key layout:
        workspaces/{workspace_id}/checkpoints/{checkpoint_id}/
            - manifest.json
            - archive.zst

    All operations are atomic at the object level. Manifests are written
    after archives to ensure checksum validation can occur.
    """

    # Static identity files that must NOT be included in checkpoints
    STATIC_IDENTITY_FILES = {
        "AGENT.md",
        "SOUL.md",
        "IDENTITY.md",
    }

    # Directory names for static identity files
    STATIC_IDENTITY_DIRS = {
        "skills",
        ".skills",
    }

    def __init__(
        self,
        s3_client: S3Client,
        bucket: str,
        endpoint: str | None = None,
    ):
        """Initialize S3 checkpoint store.

        Args:
            s3_client: Configured boto3 S3 client
            bucket: S3 bucket name for checkpoint storage
            endpoint: Optional S3 endpoint URL (for MinIO, Ceph, etc.)
        """
        self._client = s3_client
        self._bucket = bucket
        self._endpoint = endpoint

    def _get_base_key(self, workspace_id: UUID, checkpoint_id: UUID) -> str:
        """Generate deterministic base key for checkpoint objects.

        Key layout: workspaces/{workspace_id}/checkpoints/{checkpoint_id}/
        """
        return f"workspaces/{workspace_id}/checkpoints/{checkpoint_id}"

    def _get_archive_key(self, workspace_id: UUID, checkpoint_id: UUID) -> str:
        """Generate S3 key for checkpoint archive."""
        return f"{self._get_base_key(workspace_id, checkpoint_id)}/archive.zst"

    def _get_manifest_key(self, workspace_id: UUID, checkpoint_id: UUID) -> str:
        """Generate S3 key for checkpoint manifest."""
        return f"{self._get_base_key(workspace_id, checkpoint_id)}/manifest.json"

    def put_archive(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
        archive_bytes: bytes,
        manifest: CheckpointManifest,
    ) -> None:
        """Store checkpoint archive and manifest.

        Writes archive first, then manifest. Manifest includes checksum
        for integrity validation on retrieval.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID
            archive_bytes: Compressed checkpoint archive bytes
            manifest: Checkpoint metadata with checksum

        Raises:
            StorageError: If S3 operation fails
        """
        import json

        archive_key = self._get_archive_key(workspace_id, checkpoint_id)
        manifest_key = self._get_manifest_key(workspace_id, checkpoint_id)

        try:
            # Write archive first
            self._client.put_object(
                Bucket=self._bucket,
                Key=archive_key,
                Body=archive_bytes,
                ContentType="application/zstd",
                Metadata={
                    "checkpoint-id": str(checkpoint_id),
                    "workspace-id": str(workspace_id),
                },
            )

            # Write manifest with checksum reference
            manifest_json = json.dumps(manifest.to_dict(), indent=2)
            self._client.put_object(
                Bucket=self._bucket,
                Key=manifest_key,
                Body=manifest_json.encode("utf-8"),
                ContentType="application/json",
                Metadata={
                    "checkpoint-id": str(checkpoint_id),
                    "workspace-id": str(workspace_id),
                    "archive-checksum": manifest.archive_checksum,
                },
            )
        except Exception as e:
            raise StorageError(
                f"Failed to store checkpoint {checkpoint_id}: {e}"
            ) from e

    def get_archive(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
    ) -> bytes:
        """Retrieve checkpoint archive bytes.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID

        Returns:
            Archive bytes (compressed)

        Raises:
            CheckpointNotFoundError: If checkpoint doesn't exist
            StorageError: If S3 operation fails
        """
        archive_key = self._get_archive_key(workspace_id, checkpoint_id)

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=archive_key)
            return response["Body"].read()
        except self._client.exceptions.NoSuchKey:
            raise CheckpointNotFoundError(
                f"Checkpoint {checkpoint_id} not found in workspace {workspace_id}"
            )
        except Exception as e:
            raise StorageError(
                f"Failed to retrieve checkpoint {checkpoint_id}: {e}"
            ) from e

    def get_manifest(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
    ) -> CheckpointManifest:
        """Retrieve checkpoint manifest.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID

        Returns:
            CheckpointManifest with checksum and metadata

        Raises:
            CheckpointNotFoundError: If manifest doesn't exist
            StorageError: If S3 operation fails
        """
        import json

        manifest_key = self._get_manifest_key(workspace_id, checkpoint_id)

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=manifest_key)
            manifest_data = json.loads(response["Body"].read().decode("utf-8"))
            return CheckpointManifest.from_dict(manifest_data)
        except self._client.exceptions.NoSuchKey:
            raise CheckpointNotFoundError(
                f"Manifest for checkpoint {checkpoint_id} not found"
            )
        except Exception as e:
            raise StorageError(
                f"Failed to retrieve manifest for {checkpoint_id}: {e}"
            ) from e

    def head_manifest(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
    ) -> dict[str, Any] | None:
        """Check if manifest exists and return metadata.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID

        Returns:
            Object metadata dict if exists, None if not found

        Raises:
            StorageError: If S3 operation fails
        """
        manifest_key = self._get_manifest_key(workspace_id, checkpoint_id)

        try:
            response = self._client.head_object(Bucket=self._bucket, Key=manifest_key)
            return {
                "content_length": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "checksum": response.get("Metadata", {}).get("archive-checksum"),
            }
        except Exception as e:
            # Handle ClientError for 404 Not Found
            if hasattr(e, "response"):
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code in ("404", "NoSuchKey"):
                    return None
            raise StorageError(f"Failed to check manifest existence: {e}") from e

    def delete_checkpoint(
        self,
        workspace_id: UUID,
        checkpoint_id: UUID,
    ) -> None:
        """Delete checkpoint archive and manifest.

        Args:
            workspace_id: Workspace UUID
            checkpoint_id: Checkpoint UUID

        Raises:
            StorageError: If S3 operation fails
        """
        archive_key = self._get_archive_key(workspace_id, checkpoint_id)
        manifest_key = self._get_manifest_key(workspace_id, checkpoint_id)

        try:
            # Delete both objects (best effort - don't fail if one missing)
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={
                    "Objects": [
                        {"Key": archive_key},
                        {"Key": manifest_key},
                    ],
                    "Quiet": True,
                },
            )
        except Exception as e:
            raise StorageError(
                f"Failed to delete checkpoint {checkpoint_id}: {e}"
            ) from e

    @staticmethod
    def is_static_identity_path(path: str | Path) -> bool:
        """Check if path contains static identity files that should be excluded.

        Static identity files (AGENT.md, SOUL.md, IDENTITY.md, skills/)
        are mounted at sandbox creation and should not be checkpointed.

        Args:
            path: File or directory path to check

        Returns:
            True if path is a static identity file/directory
        """
        path_str = str(path)
        path_parts = Path(path_str).parts

        # Check for exact file matches
        if Path(path_str).name in S3CheckpointStore.STATIC_IDENTITY_FILES:
            return True

        # Check for static identity directories in path
        for part in path_parts:
            if part in S3CheckpointStore.STATIC_IDENTITY_DIRS:
                return True

        return False


class StorageError(Exception):
    """Raised when checkpoint storage operation fails."""

    pass


class CheckpointNotFoundError(Exception):
    """Raised when checkpoint is not found in storage."""

    pass
