---
phase: "03"
plan: "01"
subsystem: "persistence-and-checkpoint-recovery"
tags:
  - "postgresql"
  - "alembic"
  - "orm"
  - "checkpoint"
  - "audit"
  - "schema"
dependency_graph:
  requires:
    - "Phase 2.1: Bridge Agent Pack Sandbox to Picoclaw Runtime"
  provides:
    - "Phase 3 database schema foundation"
    - "Runtime persistence tables"
    - "Checkpoint metadata storage"
    - "Immutable audit logging"
  affects:
    - "Phase 3 Plan 02: Checkpoint storage service"
    - "Phase 3 Plan 03: Restore orchestration"
    - "Phase 3 Plan 04: Audit and timeline APIs"
tech_stack:
  added:
    - "PostgreSQL enum types (run_session_state, runtime_event_type, checkpoint_state, audit_event_category)"
    - "Immutable audit trigger (PostgreSQL)"
  patterns:
    - "Append-only audit logging with database-level enforcement"
    - "Active checkpoint pointer pattern (singleton per workspace)"
    - "Fallback chain for checkpoint resilience"
    - "Run timeline event tracking"
file_tracking:
  created:
    - "src/db/migrations/versions/0004_phase3_persistence_and_checkpoint_recovery.py"
    - "src/tests/smoke/test_phase3_schema_bootstrap.py"
  modified:
    - "src/db/models.py"
decisions:
  - id: "D-03-01-001"
    date: "2026-02-26"
    plan: "03-01"
    decision: "Use PostgreSQL trigger for immutable audit enforcement"
    rationale: "Database-level enforcement is fail-closed and cannot be bypassed by application bugs"
  - id: "D-03-01-002"
    date: "2026-02-26"
    plan: "03-01"
    decision: "Active checkpoint pointer as separate table with workspace unique constraint"
    rationale: "Enforces singleton pattern at database level, prevents multiple active pointers per workspace"
  - id: "D-03-01-003"
    date: "2026-02-26"
    plan: "03-01"
    decision: "Self-referential foreign key for checkpoint fallback chain"
    rationale: "Supports linked list traversal for fallback without additional tables"
  - id: "D-03-01-004"
    date: "2026-02-26"
    plan: "03-01"
    decision: "Separate runtime_events from audit_events tables"
    rationale: "Different access patterns: runtime_events for run timeline, audit_events for security/compliance"
metrics:
  duration: "~30 minutes"
  completed: "2026-02-26"
  tasks_completed: 3
  tests_added: 15
---

# Phase 3 Plan 1: Persistence Schema Foundation Summary

## Overview

Created the durable schema foundation for Phase 3 persistence and checkpoint recovery. All runtime persistence, checkpoint tracking, restore logic, and security audit guarantees now have correct data structures with immutable audit enforcement.

## What Was Built

### Database Schema

**New Tables:**
1. **`run_sessions`** - Tracks run lifecycle from queue through completion
   - Links to workspace, sandbox, and checkpoint
   - States: queued, running, paused, completed, failed, cancelled
   - Stores request/result payloads as JSON

2. **`runtime_events`** - Append-only event log for run timeline
   - Event types: session lifecycle, checkpoint operations, policy violations
   - Correlation IDs for distributed tracing
   - Indexed for timeline queries

3. **`workspace_checkpoints`** - Checkpoint metadata storage
   - Storage key reference (S3-compatible)
   - Manifest JSON for checkpoint contents
   - Fallback chain via self-referential FK
   - States: pending, in_progress, completed, failed, partial

4. **`workspace_active_checkpoints`** - Singleton active pointer per workspace
   - Unique constraint on workspace_id (singleton pattern)
   - References valid checkpoint record
   - Tracks who changed pointer and why

5. **`audit_events`** - Immutable security audit log
   - Database-level enforcement prevents UPDATE/DELETE
   - Categories: run_execution, checkpoint_management, policy_enforcement, system_operation
   - Actor and resource tracking for compliance

### Key Features

**Immutable Audit Enforcement (PostgreSQL):**
```sql
CREATE TRIGGER audit_events_immutable
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_mutation();
```

**Active Checkpoint Singleton Pattern:**
- Unique constraint on `workspace_id` ensures only one active checkpoint per workspace
- Foreign key ensures pointer always references valid checkpoint

**Query-Optimized Indexes:**
- Run session: workspace_id, state, run_id, parent_run_id
- Runtime events: run_session_id, event_type, occurred_at
- Checkpoints: workspace_id, checkpoint_id, state, created_by_run_id
- Audit: category, actor_id, resource_id, occurred_at

## Test Coverage

**15 smoke tests covering:**
- Migration chain includes revision 0004
- All Phase 3 tables exist with correct structure
- Indexes created for query patterns
- Models can be imported
- Audit events are insertable
- Audit events reject UPDATE/DELETE (PostgreSQL)
- Active checkpoint pointer has proper relationships
- Active checkpoint enforces workspace uniqueness

**Verification:**
```bash
uv run alembic upgrade head && uv run pytest src/tests/smoke/test_phase3_schema_bootstrap.py -q
# 12 passed, 3 skipped (PostgreSQL-specific tests on SQLite)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite compatibility for smoke tests**

- **Found during:** Task 3 test execution
- **Issue:** Tests used PostgreSQL-specific `NOW()` function and UUID type binding
- **Fix:** 
  - Replaced `NOW()` with Python `datetime.now(timezone.utc)`
  - Converted UUID to string for SQLite parameter binding
  - Added explicit `created_at` parameter for NOT NULL constraint
- **Files modified:** `src/tests/smoke/test_phase3_schema_bootstrap.py`
- **Commit:** `f83ce82`

## Decisions Made

| ID | Date | Decision | Rationale |
|----|------|----------|-----------|
| D-03-01-001 | 2026-02-26 | PostgreSQL trigger for immutable audit | Database-level enforcement is fail-closed |
| D-03-01-002 | 2026-02-26 | Separate active checkpoint pointer table | Enforces singleton pattern at DB level |
| D-03-01-003 | 2026-02-26 | Self-referential FK for fallback chain | Supports linked list traversal |
| D-03-01-004 | 2026-02-26 | Separate runtime_events and audit_events | Different access patterns |

## Next Phase Readiness

**Ready for:**
- Phase 3 Plan 02: Checkpoint storage service
- Phase 3 Plan 03: Restore orchestration
- Phase 3 Plan 04: Audit and timeline APIs

**Schema supports:**
- Run session tracking
- Checkpoint metadata and versioning
- Active checkpoint pointer management
- Immutable audit logging
- Restore fallback chains
- Run timeline queries

## Commits

| Hash | Message |
|------|---------|
| ad67e4d | feat(03-01): add Phase 3 ORM models |
| ea90b2a | feat(03-01): create Alembic migration |
| df34dfe | test(03-01): add smoke checks |
| f83ce82 | fix(03-01): make smoke tests database-agnostic |

---
*Completed: 2026-02-26*
*Duration: ~30 minutes*
