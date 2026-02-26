---
phase: "03"
plan: "03"
subsystem: persistence
tags: ["persistence", "checkpoint", "repository", "audit", "runtime-events"]
dependency_graph:
  requires: ["03-01", "03-02"]
  provides: ["run-session-repository", "runtime-event-repository", "workspace-checkpoint-repository", "audit-event-repository", "runtime-persistence-service", "workspace-checkpoint-service"]
  affects: ["03-04", "03-05"]
tech-stack:
  added: []
  patterns: ["Repository Pattern", "Service Layer", "Append-Only Audit", "Active Checkpoint Pointer"]
key-files:
  created:
    - src/db/repositories/run_session_repository.py
    - src/db/repositories/runtime_event_repository.py
    - src/db/repositories/workspace_checkpoint_repository.py
    - src/db/repositories/audit_event_repository.py
    - src/services/runtime_persistence_service.py
    - src/services/workspace_checkpoint_service.py
    - src/tests/integration/test_phase3_persistence_writes.py
  modified:
    - src/db/repositories/__init__.py
    - src/services/run_service.py
decisions:
  - id: "D-03-03-001"
    date: "2026-02-26"
    decision: "Guest persistence raises explicit GuestPersistenceError rather than silently skipping"
    rationale: "Fail-fast principle - explicit errors are better than silent data loss"
  - id: "D-03-03-002"
    date: "2026-02-26"
    decision: "Active checkpoint pointer auto-advances on successful checkpoint completion"
    rationale: "Per 03-CONTEXT: 'Active revision pointer auto-advances to the newest successful checkpoint'"
  - id: "D-03-03-003"
    date: "2026-02-26"
    decision: "Policy violations are always logged even for guests (security requirement)"
    rationale: "Security events must be recorded regardless of principal type"
  - id: "D-03-03-004"
    date: "2026-02-26"
    decision: "Run session ID is tracked through execute_with_routing for persistence updates"
    rationale: "Need to correlate runtime execution with durable session records"
  - id: "D-03-03-005"
    date: "2026-02-26"
    decision: "Checkpoint metadata-only creation for testing bypasses S3 storage"
    rationale: "Enables fast unit tests without S3 infrastructure"
metrics:
  duration: "2h 30m"
  completed: "2026-02-26"
  tests_passed: 32
  tests_total: 32
---

# Phase 3 Plan 03: Runtime Persistence and Checkpoint Write Paths Summary

## Overview

Wired runtime persistence and checkpoint write paths into real run execution. This plan delivers PERS-01 and the write half of PERS-02/PERS-03 by making successful non-guest runs durable and checkpoint-capable.

## What Was Built

### 1. Repository Layer (4 new repositories)

| Repository | Purpose | Key Methods |
|------------|---------|-------------|
| `RunSessionRepository` | Run session CRUD and lifecycle | `create()`, `mark_running()`, `mark_completed()`, `mark_failed()` |
| `RuntimeEventRepository` | Append-only runtime events | `create()`, `list_by_run_session()`, log helpers |
| `WorkspaceCheckpointRepository` | Checkpoint metadata and active pointer | `create()`, `advance_active_checkpoint()`, `get_active_checkpoint()` |
| `AuditEventRepository` | Immutable audit events | `create()` (no update/delete), category-specific log helpers |

### 2. Service Layer (2 new services)

#### RuntimePersistenceService
- **Purpose**: Durable persistence for non-guest run executions
- **Guest Guard**: Raises `GuestPersistenceError` for guest operations
- **Features**:
  - Run session lifecycle management
  - Runtime event logging (append-only)
  - Audit event append-only logging
  - Policy violation logging (always logged, even for guests)

#### WorkspaceCheckpointService
- **Purpose**: Checkpoint write flow with S3 integration
- **Guest Guard**: Raises `GuestCheckpointError` for guest checkpoints
- **Features**:
  - Full checkpoint creation with S3 storage
  - Metadata-only creation for testing
  - Active checkpoint pointer auto-advance
  - Fallback chain traversal support

### 3. Run Service Integration

Updated `RunService.execute_with_routing()` to:
1. Initialize `RuntimePersistenceService` for database session
2. Create run session records for non-guest runs with successful routing
3. Update run session state based on execution result (completed/failed)
4. Release lease deterministically after execution

### 4. Test Coverage (32 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestRunSessionRepository` | 7 | CRUD, state transitions, listing |
| `TestRuntimeEventRepository` | 4 | Event creation, listing, counting |
| `TestWorkspaceCheckpointRepository` | 6 | Checkpoint lifecycle, active pointer |
| `TestAuditEventRepository` | 4 | Audit event creation, category filtering |
| `TestRuntimePersistenceService` | 4 | Non-guest persistence, guest error handling |
| `TestWorkspaceCheckpointService` | 5 | Checkpoint creation, pointer management |
| `TestEndToEndPersistence` | 2 | Full run execution with persistence |

## Truths Verified

✅ **"Non-guest run execution writes run/session metadata and runtime events to Postgres."**
- `RuntimePersistenceService.create_run_session()` creates run sessions for non-guest principals
- `mark_run_completed()` / `mark_run_failed()` update session state
- Runtime events are logged via `RuntimeEventRepository`

✅ **"Milestone checkpoint writes persist archive metadata and auto-advance the active checkpoint pointer to newest successful revision."**
- `WorkspaceCheckpointService.create_checkpoint()` persists checkpoint metadata
- `advance_active_checkpoint()` updates the active pointer
- Auto-advance on checkpoint completion per D-03-03-002

✅ **"Checkpoint and runtime persistence operations append audit events without mutating existing audit rows."**
- All persistence operations call audit log methods
- `AuditEventRepository` only exposes CREATE (no UPDATE/DELETE)
- Database trigger prevents mutation (from 03-01)

## Key Design Decisions

### Guest Mode Explicit Errors
Guest attempts to persist raise `GuestPersistenceError` rather than silently skipping. This is fail-fast behavior - explicit errors are better than mysterious data loss.

### Auto-Advance Active Pointer
Per 03-CONTEXT decision: "Active revision pointer auto-advances to the newest successful checkpoint." This is implemented in `WorkspaceCheckpointRepository.advance_active_checkpoint()`.

### Security Events Always Logged
Policy violations are logged via `log_policy_violation()` even for guest principals. Security audit requirements take precedence over guest privacy for enforcement events.

### Persistence Failures Don't Fail Runs
Persistence operations are wrapped in try/except blocks in `execute_with_routing()`. A database error during persistence shouldn't cause a successful run to fail.

## Files Modified

```
src/db/repositories/__init__.py
  + Exports: RunSessionRepository, RuntimeEventRepository,
    WorkspaceCheckpointRepository, AuditEventRepository

src/services/run_service.py
  + Imports: RuntimePersistenceService, GuestPersistenceError
  + __init__: Accepts optional persistence_service parameter
  + execute_with_routing(): Persistence hooks for session creation,
    state updates, and lease release
  + _get_principal_id(): Helper to extract principal identity
```

## API Changes

### New Exceptions
```python
class GuestPersistenceError(Exception):
    """Guest runs cannot be persisted."""

class GuestCheckpointError(Exception):
    """Guest runs cannot create checkpoints."""

class CheckpointPersistenceError(Exception):
    """Checkpoint storage operation failed."""
```

### RunService Signature Change
```python
# Before
def __init__(self, enforcer=None, lifecycle_service=None)

# After
def __init__(self, enforcer=None, lifecycle_service=None, persistence_service=None)
```

## Deviations from Plan

None - plan executed exactly as written. All tasks completed:
- Task 1: ✅ 4 repositories implemented
- Task 2: ✅ 2 services built
- Task 3: ✅ Services integrated + 32 integration tests

## Next Steps

Plan 03-04 will implement checkpoint restore paths and read-side APIs:
- Restore checkpoint on workspace cold start
- Checkpoint listing and retrieval APIs
- Run timeline queries

## Verification Results

```bash
$ uv run pytest src/tests/integration/test_phase3_persistence_writes.py -q
32 passed, 210 warnings in 1.73s
```

All tests pass. Warnings are deprecation notices for `datetime.utcnow()` (pre-existing in codebase).
