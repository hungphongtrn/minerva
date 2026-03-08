# Phase 03 Plan 02: Object-Storage Checkpoint Primitives - Summary

## Overview

Implementation of S3-compatible checkpoint storage primitives and archive tooling for Phase 3 (Persistence and Checkpoint Recovery). This plan delivers the foundational storage layer required for PERS-02 and PERS-03 checkpoint persistence requirements.

**Phase:** 03-persistence-and-checkpoint-recovery  
**Plan:** 02  
**Status:** ✅ Complete  
**Completed:** 2026-02-26  

---

## What Was Built

### 1. Checkpoint Storage Configuration (`src/config/settings.py`)

Added comprehensive checkpoint storage configuration:

- **CHECKPOINT_S3_BUCKET** - S3 bucket name for checkpoint archives
- **CHECKPOINT_S3_ENDPOINT** - S3-compatible endpoint URL (AWS, MinIO, Ceph)
- **CHECKPOINT_S3_REGION** - AWS region (default: us-east-1)
- **CHECKPOINT_S3_ACCESS_KEY** / **CHECKPOINT_S3_SECRET_KEY** - Authentication
- **CHECKPOINT_MILESTONE_INTERVAL_SECONDS** - Auto-checkpoint interval (default: 300s)
- **CHECKPOINT_SAFETY_MARGIN_BYTES** - Max checkpoint size (default: 100MB)
- **CHECKPOINT_ENABLED** - Global toggle (default: False for dev safety)

### 2. S3 Checkpoint Store (`src/infrastructure/checkpoints/s3_checkpoint_store.py`)

S3-compatible storage implementation with deterministic key layout:

```
workspaces/{workspace_id}/checkpoints/{checkpoint_id}/
├── archive.zst          # Compressed checkpoint archive
└── manifest.json        # Metadata with checksum
```

**Key Features:**
- Deterministic key generation for idempotent operations
- Put/get/head/delete operations for checkpoint lifecycle
- Manifest with SHA-256 checksum for integrity validation
- Support for AWS S3 and S3-compatible endpoints (MinIO, Ceph)
- Static identity file detection (AGENT.md, SOUL.md, IDENTITY.md, skills/)

### 3. Checkpoint Archive Service (`src/services/checkpoint_archive_service.py`)

Archive pack/unpack service with scope enforcement:

**Archive Format:**
- Compression: zstandard (zstd) for speed/ratio balance
- Container: tar for structured storage
- Contents:
  - `checkpoint.json` - Session state and metadata
  - `checksum.sha256` - Integrity checksum placeholder
  - `checkpoint.meta.json` - Version and scope documentation

**Checkpoint Scope Rules:**
- **INCLUDES:** Dynamic session state, conversation history, runtime variables
- **EXCLUDES:** Static identity files (AGENT.md, SOUL.md, IDENTITY.md, skills/)

### 4. Comprehensive Test Suite (`src/tests/services/test_checkpoint_storage_and_archive.py`)

32 tests covering:
- Deterministic S3 key generation (4 tests)
- SHA-256 checksum computation and validation (3 tests)
- Checkpoint scope filtering for static identity files (6 tests)
- Archive pack/unpack roundtrip (3 tests)
- S3 store operations with mocked client (4 tests)
- Archive service integration with store (3 tests)
- Manifest serialization (2 tests)
- Failure handling: missing objects, corruption, checksum mismatch (4 tests)
- Archive result structure (3 tests)

---

## Key Design Decisions

### D-03-02-001: Deterministic Key Layout
**Decision:** Use hierarchical key structure `workspaces/{uuid}/checkpoints/{uuid}/`

**Rationale:**
- Natural workspace-scoped organization
- Enables efficient listing and cleanup per workspace
- Checkpoint ID uniqueness preserved within workspace boundary
- Aligns with Picoclaw's workspace-centric tenancy model

### D-03-02-002: Manifest-First Integrity
**Decision:** Write manifest after archive with embedded checksum

**Rationale:**
- Manifest presence signals complete checkpoint
- Checksum in manifest enables retrieval validation
- S3 metadata carries checksum for quick head checks
- Prevents partial checkpoint reads

### D-03-02-003: Static Identity Exclusion
**Decision:** Explicitly exclude AGENT.md, SOUL.md, IDENTITY.md, and skills/ from checkpoints

**Rationale:**
- Per Picoclaw runtime invariants, static files are mounted at sandbox creation
- Checkpoint data should only capture runtime memory/session state
- Reduces checkpoint size and prevents accidental static file modification
- Alignment with Phase 3 scope (memory/session state only)

### D-03-02-004: zstandard Compression
**Decision:** Use zstandard (zstd) level 3 for archive compression

**Rationale:**
- Superior speed/compression ratio vs gzip
- Industry standard (Facebook/Meta, AWS, etc.)
- Python native support via zstandard library
- Level 3 balances speed and size for typical session data

### D-03-02-005: Fail-Closed Configuration
**Decision:** CHECKPOINT_ENABLED defaults to False

**Rationale:**
- Prevents accidental checkpoint persistence in development
- Requires explicit opt-in for production deployments
- Safe local development without S3 configuration
- Fail-closed security principle

---

## Artifacts Created

### Source Files
- `src/infrastructure/checkpoints/__init__.py` - Module exports
- `src/infrastructure/checkpoints/s3_checkpoint_store.py` (351 lines)
  - `S3CheckpointStore` class
  - `CheckpointManifest` dataclass
  - `StorageError`, `CheckpointNotFoundError` exceptions
- `src/services/checkpoint_archive_service.py` (402 lines)
  - `CheckpointArchiveService` class
  - `SessionState` dataclass
  - `CheckpointArchiveResult` dataclass
  - `ChecksumMismatchError`, `ArchiveCorruptedError` exceptions

### Test Files
- `src/tests/services/test_checkpoint_storage_and_archive.py` (563 lines)
  - 32 tests, all passing

### Configuration Updates
- `pyproject.toml` - Added boto3, zstandard dependencies
- `src/config/settings.py` - Added CHECKPOINT_* settings
- `.env.example` - Added checkpoint configuration examples

---

## Verification

All tests pass:

```bash
$ uv run pytest src/tests/services/test_checkpoint_storage_and_archive.py -q
................................
32 passed in 3.59s
```

### Test Coverage
- ✅ Deterministic key layout
- ✅ Checksum computation and validation
- ✅ Static identity file exclusion
- ✅ Archive pack/unpack roundtrip
- ✅ S3 store operations (mocked)
- ✅ Failure handling (404, corruption, checksum mismatch)
- ✅ Manifest serialization

---

## Deviations from Plan

None - plan executed exactly as written.

---

## Technical Debt & Notes

### For Future Phases

1. **S3 Client Lifecycle** - Currently accepts pre-configured S3 client. Future work may add connection pooling and retry configuration.

2. **Streaming Archives** - Current implementation loads full archive into memory. For very large checkpoints (>100MB), streaming upload/download may be needed.

3. **Incremental Checkpoints** - Current implementation creates full checkpoints. Future optimization may implement differential/delta checkpoints.

4. **Encryption at Rest** - Checksums provide integrity but not confidentiality. Consider S3 SSE or client-side encryption for sensitive data.

---

## Next Phase Readiness

This plan enables:
- ✅ Checkpoint persistence to S3-compatible storage
- ✅ Deterministic key generation for workspace-scoped checkpoints
- ✅ Archive integrity validation via SHA-256 checksums
- ✅ Static identity file exclusion (scope enforcement)

**Ready for:**
- Plan 03-03: Checkpoint registry and pointer management
- Plan 03-04: Checkpoint restore and recovery workflows
- Plan 03-05: Acceptance tests for checkpoint lifecycle

---

## Dependencies

**Added:**
- `boto3>=1.35.0` - AWS S3 SDK
- `zstandard>=0.23.0` - Compression library

**No breaking changes** to existing dependencies.

---

## Performance Characteristics

- **Key Generation:** O(1) - String formatting only
- **Archive Creation:** O(n) where n = session state size
- **Compression:** zstd level 3 (balanced speed/ratio)
- **Checksum:** SHA-256 computed once on compressed bytes
- **S3 Operations:** Standard PUT/GET/HEAD latency

---

## Security Considerations

- ✅ Static identity files excluded from checkpoints
- ✅ SHA-256 checksums for integrity validation
- ✅ S3 credentials from environment (not hardcoded)
- ✅ Fail-closed: CHECKPOINT_ENABLED defaults to False
- ⚠️ No encryption at rest (relies on S3 SSE or transport TLS)
- ⚠️ No checkpoint size limits enforced (configurable via CHECKPOINT_SAFETY_MARGIN_BYTES)

---

## API Usage Example

```python
from uuid import uuid4
from src.infrastructure.checkpoints import S3CheckpointStore
from src.services.checkpoint_archive_service import CheckpointArchiveService, SessionState
import boto3

# Initialize store
s3_client = boto3.client('s3')
store = S3CheckpointStore(s3_client, bucket="checkpoints")

# Create archive service
archive_service = CheckpointArchiveService(store=store)

# Create checkpoint
session = SessionState(
    session_data={"counter": 42},
    conversation_history=[{"role": "user", "content": "Hello"}],
)

result = archive_service.save_checkpoint(
    workspace_id=uuid4(),
    agent_pack_id=uuid4(),
    session_state=session,
)

# Later: restore checkpoint
restored = archive_service.load_checkpoint(workspace_id, checkpoint_id)
```

---

## Commits

- `7885665` - chore(03-02): add checkpoint storage dependencies and configuration surface
- `076567a` - feat(03-02): build S3 checkpoint store and archive service with deterministic keying
- `cf0d8c2` - test(03-02): add service tests for storage correctness and failure handling

---

*Summary generated: 2026-02-26*
