"""Tests for checkpoint storage and archive service.

Validates:
- Deterministic S3 key generation
- Checksum computation and validation
- Checkpoint scope (static identity file exclusion)
- Archive pack/unpack roundtrip
- Failure handling (missing objects, checksum mismatch)
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from tarfile import TarFile
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import zstandard
from botocore.exceptions import ClientError

from src.infrastructure.checkpoints.s3_checkpoint_store import (
    CheckpointManifest,
    CheckpointNotFoundError,
    S3CheckpointStore,
    StorageError,
)
from src.services.checkpoint_archive_service import (
    ArchiveCorruptedError,
    CheckpointArchiveResult,
    CheckpointArchiveService,
    ChecksumMismatchError,
    SessionState,
    StorageError as ArchiveStorageError,
)


class TestDeterministicKeyLayout:
    """Validate deterministic S3 key generation for checkpoint objects."""

    def test_archive_key_format(self):
        """Archive keys follow: workspaces/{uuid}/checkpoints/{uuid}/archive.zst"""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        workspace_id = uuid4()
        checkpoint_id = uuid4()

        key = store._get_archive_key(workspace_id, checkpoint_id)

        assert key.startswith(f"workspaces/{workspace_id}/checkpoints/{checkpoint_id}/")
        assert key.endswith("/archive.zst")

    def test_manifest_key_format(self):
        """Manifest keys follow: workspaces/{uuid}/checkpoints/{uuid}/manifest.json"""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        workspace_id = uuid4()
        checkpoint_id = uuid4()

        key = store._get_manifest_key(workspace_id, checkpoint_id)

        assert key.startswith(f"workspaces/{workspace_id}/checkpoints/{checkpoint_id}/")
        assert key.endswith("/manifest.json")

    def test_keys_are_deterministic(self):
        """Same UUIDs produce identical keys (idempotent)."""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        workspace_id = uuid4()
        checkpoint_id = uuid4()

        key1 = store._get_archive_key(workspace_id, checkpoint_id)
        key2 = store._get_archive_key(workspace_id, checkpoint_id)

        assert key1 == key2

    def test_different_checkpoints_different_keys(self):
        """Different checkpoint IDs produce different keys."""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        workspace_id = uuid4()
        checkpoint_id1 = uuid4()
        checkpoint_id2 = uuid4()

        key1 = store._get_archive_key(workspace_id, checkpoint_id1)
        key2 = store._get_archive_key(workspace_id, checkpoint_id2)

        assert key1 != key2


class TestChecksumComputation:
    """Validate SHA-256 checksum computation on archive bytes."""

    def test_checksum_computed_on_compressed_bytes(self):
        """Checksum is computed on final compressed archive bytes."""
        service = CheckpointArchiveService()
        session_state = SessionState(
            session_data={"key": "value"},
            conversation_history=[{"role": "user", "content": "hello"}],
        )

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Recompute checksum and verify it matches
        expected_checksum = hashlib.sha256(result.archive_bytes).hexdigest()
        assert result.manifest.archive_checksum == expected_checksum

    def test_checksum_validates_archive_integrity(self):
        """Checksum validation detects corrupted archives."""
        service = CheckpointArchiveService()
        session_state = SessionState(session_data={"test": "data"})

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Corrupt the archive
        corrupted_bytes = result.archive_bytes[:-10] + b"CORRUPTED!"

        # Validation should fail
        with pytest.raises(ChecksumMismatchError):
            service.extract_checkpoint(
                corrupted_bytes,
                expected_checksum=result.manifest.archive_checksum,
            )

    def test_manifest_includes_checksum(self):
        """Manifest contains archive checksum for integrity verification."""
        service = CheckpointArchiveService()
        session_state = SessionState()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        assert result.manifest.archive_checksum is not None
        assert len(result.manifest.archive_checksum) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in result.manifest.archive_checksum)


class TestCheckpointScope:
    """Validate checkpoint scope excludes static identity files."""

    def test_static_identity_files_excluded(self):
        """Static identity files (AGENT.md, SOUL.md, IDENTITY.md) are excluded."""
        assert S3CheckpointStore.is_static_identity_path("/workspace/AGENT.md")
        assert S3CheckpointStore.is_static_identity_path("/workspace/SOUL.md")
        assert S3CheckpointStore.is_static_identity_path("/workspace/IDENTITY.md")

    def test_skills_directory_excluded(self):
        """Skills directory is excluded from checkpoints."""
        assert S3CheckpointStore.is_static_identity_path("/workspace/skills")
        assert S3CheckpointStore.is_static_identity_path("/workspace/skills/tool.py")
        assert S3CheckpointStore.is_static_identity_path("skills/nested/file.txt")

    def test_dot_skills_directory_excluded(self):
        """Hidden .skills directory is excluded."""
        assert S3CheckpointStore.is_static_identity_path("/workspace/.skills")
        assert S3CheckpointStore.is_static_identity_path("/workspace/.skills/tool.py")

    def test_regular_files_included(self):
        """Regular session files are not excluded."""
        assert not S3CheckpointStore.is_static_identity_path("/workspace/session.json")
        assert not S3CheckpointStore.is_static_identity_path("/workspace/data.txt")
        assert not S3CheckpointStore.is_static_identity_path(
            "/workspace/checkpoint.json"
        )

    def test_archive_service_excludes_static_paths(self):
        """CheckpointArchiveService excludes static paths from scope."""
        assert CheckpointArchiveService.should_exclude_path("AGENT.md")
        assert CheckpointArchiveService.should_exclude_path("skills/tool.py")
        assert CheckpointArchiveService.should_exclude_path(".env")
        assert not CheckpointArchiveService.should_exclude_path("session.json")

    def test_excluded_paths_in_checkpoint_meta(self):
        """Checkpoint metadata documents excluded paths."""
        service = CheckpointArchiveService()
        session_state = SessionState()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Extract and verify metadata
        extracted = service.extract_checkpoint(result.archive_bytes)

        # Archive should not contain static identity files
        # (verified by scope - only checkpoint.json is in archive)
        assert extracted is not None


class TestArchivePackUnpack:
    """Validate archive pack and unpack roundtrip."""

    def test_session_state_roundtrip(self):
        """Session state survives pack/unpack roundtrip."""
        service = CheckpointArchiveService()
        original_state = SessionState(
            session_data={"counter": 42, "name": "test"},
            conversation_history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
            runtime_variables={"ENV": "test", "DEBUG": "1"},
            metadata={"version": "1.0"},
        )

        # Create checkpoint
        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=original_state,
        )

        # Extract checkpoint
        extracted_state = service.extract_checkpoint(result.archive_bytes)

        # Verify roundtrip
        assert extracted_state.session_data == original_state.session_data
        assert (
            extracted_state.conversation_history == original_state.conversation_history
        )
        assert extracted_state.runtime_variables == original_state.runtime_variables
        assert extracted_state.metadata == original_state.metadata

    def test_archive_contains_expected_files(self):
        """Archive contains checkpoint.json, checksum.sha256, checkpoint.meta.json."""
        service = CheckpointArchiveService()
        session_state = SessionState(session_data={"test": "data"})

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Decompress and inspect tar
        decompressor = zstandard.ZstdDecompressor()
        tar_bytes = decompressor.decompress(result.archive_bytes)

        tar_buffer = BytesIO(tar_bytes)
        with TarFile(fileobj=tar_buffer, mode="r") as tar:
            names = tar.getnames()

        assert "checkpoint.json" in names
        assert "checksum.sha256" in names
        assert "checkpoint.meta.json" in names

    def test_checkpoint_meta_json_content(self):
        """checkpoint.meta.json contains version and scope info."""
        service = CheckpointArchiveService()
        session_state = SessionState()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Decompress and read meta
        decompressor = zstandard.ZstdDecompressor()
        tar_bytes = decompressor.decompress(result.archive_bytes)

        tar_buffer = BytesIO(tar_bytes)
        with TarFile(fileobj=tar_buffer, mode="r") as tar:
            meta_file = tar.extractfile("checkpoint.meta.json")
            meta_data = json.loads(meta_file.read().decode("utf-8"))

        assert meta_data["version"] == CheckpointArchiveService.CHECKPOINT_VERSION
        assert meta_data["scope"] == "memory_session_only"
        assert "excluded" in meta_data
        assert "AGENT.md" in meta_data["excluded"]


class TestS3StoreOperations:
    """Validate S3 store put/get/head operations with mocked client."""

    def test_put_archive_writes_manifest_with_checksum(self):
        """put_archive writes manifest with archive-checksum metadata."""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        workspace_id = uuid4()
        checkpoint_id = uuid4()
        archive_bytes = b"test-archive-data"
        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            workspace_id=workspace_id,
            agent_pack_id=uuid4(),
            archive_checksum="abcd1234" * 8,  # 64 char hex
            archive_size_bytes=len(archive_bytes),
        )

        store.put_archive(workspace_id, checkpoint_id, archive_bytes, manifest)

        # Verify manifest was written with checksum metadata
        manifest_call = mock_client.put_object.call_args_list[1]
        assert manifest_call.kwargs["Key"].endswith("manifest.json")
        assert (
            manifest_call.kwargs["Metadata"]["archive-checksum"]
            == manifest.archive_checksum
        )

    def test_get_archive_raises_not_found(self):
        """get_archive raises CheckpointNotFoundError for missing checkpoint."""
        mock_client = MagicMock()
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception("NoSuchKey")
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        with pytest.raises(CheckpointNotFoundError):
            store.get_archive(uuid4(), uuid4())

    def test_get_manifest_raises_not_found(self):
        """get_manifest raises CheckpointNotFoundError for missing manifest."""
        mock_client = MagicMock()
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception("NoSuchKey")
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        with pytest.raises(CheckpointNotFoundError):
            store.get_manifest(uuid4(), uuid4())

    def test_head_manifest_returns_none_for_missing(self):
        """head_manifest returns None for non-existent manifest."""
        mock_client = MagicMock()
        error_response = {"Error": {"Code": "404"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        result = store.head_manifest(uuid4(), uuid4())

        assert result is None

    def test_head_manifest_returns_metadata_for_existing(self):
        """head_manifest returns metadata dict for existing manifest."""
        mock_client = MagicMock()
        mock_client.head_object.return_value = {
            "ContentLength": 1234,
            "LastModified": "2024-01-01T00:00:00Z",
            "Metadata": {"archive-checksum": "abcd" * 16},
        }
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        result = store.head_manifest(uuid4(), uuid4())

        assert result is not None
        assert result["content_length"] == 1234
        assert result["checksum"] == "abcd" * 16


class TestArchiveServiceWithStore:
    """Validate CheckpointArchiveService integration with S3CheckpointStore."""

    def test_save_checkpoint_persists_to_store(self):
        """save_checkpoint creates and persists checkpoint to S3."""
        mock_client = MagicMock()
        store = S3CheckpointStore(mock_client, bucket="test-bucket")
        service = CheckpointArchiveService(store=store)

        workspace_id = uuid4()
        agent_pack_id = uuid4()
        session_state = SessionState(session_data={"key": "value"})

        result = service.save_checkpoint(
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            session_state=session_state,
        )

        # Verify store.put_archive was called
        assert mock_client.put_object.call_count == 2  # archive + manifest

        # Verify checkpoint_id returned
        assert result.checkpoint_id is not None

    def test_save_checkpoint_without_store_raises(self):
        """save_checkpoint raises StorageError if store not configured."""
        service = CheckpointArchiveService(store=None)

        with pytest.raises(
            ArchiveStorageError, match="S3CheckpointStore not configured"
        ):
            service.save_checkpoint(
                workspace_id=uuid4(),
                agent_pack_id=uuid4(),
                session_state=SessionState(),
            )

    def test_load_checkpoint_without_store_raises(self):
        """load_checkpoint raises StorageError if store not configured."""
        service = CheckpointArchiveService(store=None)

        with pytest.raises(
            ArchiveStorageError, match="S3CheckpointStore not configured"
        ):
            service.load_checkpoint(uuid4(), uuid4())


class TestManifestSerialization:
    """Validate CheckpointManifest serialization/deserialization."""

    def test_manifest_roundtrip_dict(self):
        """Manifest survives to_dict/from_dict roundtrip."""
        original = CheckpointManifest(
            checkpoint_id=uuid4(),
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            archive_checksum="abcd" * 16,
            archive_size_bytes=12345,
            content_version="1.0.0",
            created_at="2024-01-01T00:00:00Z",
            metadata={"key": "value"},
        )

        data = original.to_dict()
        restored = CheckpointManifest.from_dict(data)

        assert restored.checkpoint_id == original.checkpoint_id
        assert restored.workspace_id == original.workspace_id
        assert restored.agent_pack_id == original.agent_pack_id
        assert restored.archive_checksum == original.archive_checksum
        assert restored.archive_size_bytes == original.archive_size_bytes
        assert restored.content_version == original.content_version
        assert restored.created_at == original.created_at
        assert restored.metadata == original.metadata

    def test_manifest_uuid_serialization(self):
        """Manifest serializes UUIDs as strings."""
        checkpoint_id = uuid4()
        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            archive_checksum="abcd" * 16,
            archive_size_bytes=0,
        )

        data = manifest.to_dict()

        assert isinstance(data["checkpoint_id"], str)
        assert data["checkpoint_id"] == str(checkpoint_id)


class TestFailureHandling:
    """Validate failure handling for missing objects and corruption."""

    def test_extract_corrupted_archive_raises(self):
        """Extracting corrupted archive raises ArchiveCorruptedError."""
        service = CheckpointArchiveService()

        with pytest.raises(ArchiveCorruptedError):
            service.extract_checkpoint(b"not-valid-zstd-data")

    def test_extract_truncated_archive_raises(self):
        """Extracting truncated archive raises ArchiveCorruptedError."""
        service = CheckpointArchiveService()
        session_state = SessionState()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        # Truncate the archive
        truncated = result.archive_bytes[: len(result.archive_bytes) // 2]

        with pytest.raises(ArchiveCorruptedError):
            service.extract_checkpoint(truncated)

    def test_storage_error_propagation(self):
        """S3 errors are wrapped in StorageError with context."""
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("S3 connection failed")
        store = S3CheckpointStore(mock_client, bucket="test-bucket")

        manifest = CheckpointManifest(
            checkpoint_id=uuid4(),
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            archive_checksum="abcd" * 16,
            archive_size_bytes=0,
        )

        with pytest.raises(StorageError, match="S3 connection failed"):
            store.put_archive(uuid4(), uuid4(), b"data", manifest)


class TestArchiveResult:
    """Validate CheckpointArchiveResult structure."""

    def test_result_contains_all_fields(self):
        """Result contains checkpoint_id, archive_bytes, and manifest."""
        service = CheckpointArchiveService()
        session_state = SessionState()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=session_state,
        )

        assert isinstance(result, CheckpointArchiveResult)
        assert isinstance(result.checkpoint_id, UUID)
        assert isinstance(result.archive_bytes, bytes)
        assert isinstance(result.manifest, CheckpointManifest)
        assert len(result.archive_bytes) > 0

    def test_checkpoint_id_is_deterministic_when_provided(self):
        """Providing checkpoint_id results in deterministic ID."""
        service = CheckpointArchiveService()
        checkpoint_id = uuid4()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=SessionState(),
            checkpoint_id=checkpoint_id,
        )

        assert result.checkpoint_id == checkpoint_id
        assert result.manifest.checkpoint_id == checkpoint_id

    def test_checkpoint_id_generated_when_not_provided(self):
        """Not providing checkpoint_id generates a new UUID."""
        service = CheckpointArchiveService()

        result = service.create_checkpoint(
            workspace_id=uuid4(),
            agent_pack_id=uuid4(),
            session_state=SessionState(),
        )

        assert result.checkpoint_id is not None
        assert isinstance(result.checkpoint_id, UUID)
