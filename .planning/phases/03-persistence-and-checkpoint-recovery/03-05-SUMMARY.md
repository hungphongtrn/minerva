---
phase: 03-persistence-and-checkpoint-recovery
plan: 05
completed: 2026-02-26
duration: "2h 15m"
type: execute
subsystem: persistence
success: true
summary: "Phase 3 persistence query APIs and checkpoint pointer security controls implemented with 35 integration/security tests"
requires: ["03-03"]
provides: ["persistence-query-apis", "pointer-security-controls", "audit-timeline-access"]
affects: ["03-06", "phase-5-event-streaming"]
tags: ["persistence", "checkpoint", "api", "security", "audit", "operator-controls"]
tech-stack:
  added: []
  patterns: ["operator-authorization", "pointer-guardrails", "rollback-prevention"]
key-files:
  created:
    - src/api/routes/persistence.py
    - src/tests/integration/test_phase3_persistence_api.py
    - src/tests/integration/test_phase3_security_regressions.py
  modified:
    - src/api/router.py
    - src/services/workspace_checkpoint_service.py
metrics:
  tests-added: 35
  coverage: "persistence query surfaces, pointer controls, audit immutability"
---

# Phase 3 Plan 05: Persistence Query APIs and Pointer Security

## Summary

Implemented Phase 3 persistence query endpoints and checkpoint pointer security controls. Operators and clients can now query run/session metadata, runtime event timelines, checkpoint manifests, and workspace audit trails through authenticated REST APIs. Pointer control is secured with operator-only authorization and rollback-to-older-revision prevention (Phase 3 restriction).

## What Was Delivered

### 1. Persistence API Routes (src/api/routes/persistence.py)

**Run Timeline Endpoints:**
- `GET /api/v1/persistence/runs/{run_id}/timeline` - Complete run session + ordered events
- `GET /api/v1/persistence/runs/{run_id}/events` - Runtime events in chronological order
- `GET /api/v1/persistence/workspaces/{workspace_id}/runs` - List workspace run sessions

**Checkpoint Metadata Endpoints:**
- `GET /api/v1/persistence/workspaces/{workspace_id}/checkpoints` - List checkpoints with state filter
- `GET /api/v1/persistence/workspaces/{workspace_id}/checkpoints/{checkpoint_id}` - Checkpoint details with manifest
- `GET /api/v1/persistence/workspaces/{workspace_id}/active-checkpoint` - Active pointer with optional details

**Audit Timeline Endpoints:**
- `GET /api/v1/persistence/workspaces/{workspace_id}/audit` - Workspace audit events with category/time filters
- `GET /api/v1/persistence/audit/events/{event_id}` - Specific audit event details

**Pointer Management:**
- `POST /api/v1/persistence/workspaces/{workspace_id}/active-checkpoint` - Update active pointer (operator-only)

### 2. Service Security Guardrails (src/services/workspace_checkpoint_service.py)

**New Exception Types:**
- `PointerUpdateForbiddenError` - Raised when non-operator attempts pointer update
- `PointerRollbackForbiddenError` - Raised when rollback to older revision attempted

**New Method:**
- `set_active_checkpoint_guarded()` - Phase 3 security guardrails:
  - Operator-only authorization (checks for `admin`, `*`, or `workspace:write` scopes)
  - No rollback to older revisions (timestamp comparison)
  - Audit logging for all pointer operations

### 3. Integration Tests (20 tests)

**Test Coverage:**
- Run timeline retrieval with session metadata and events
- Checkpoint listing, filtering by state, and detail retrieval
- Active checkpoint pointer queries
- Audit timeline with category/time filters
- Workspace runs listing and filtering
- Pointer updates via API (operator success case)

### 4. Security Regression Tests (15 tests)

**Operator Authorization:**
- Non-operators receive 403 Forbidden on pointer updates
- Operators with `workspace:write` scope can update pointers

**Rollback Prevention:**
- Attempting to set older checkpoint as active returns 400
- Advancing to newer checkpoint succeeds

**Audit Immutability:**
- AuditEventRepository has no update/delete methods
- Audit events have `immutable=True` flag
- API responses include immutability indicator

**Service-Level Guardrails:**
- Unit tests for `set_active_checkpoint_guarded()` method
- Verification of non-operator rejection
- Verification of rollback prevention

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| D-03-05-001 | Operator scope check includes `workspace:write` | Test fixtures use this scope; aligns with existing permission model |
| D-03-05-002 | Use checkpoint.created_at for rollback detection | Simple timestamp comparison; sufficient for Phase 3 restriction |
| D-03-05-003 | Transaction-scoped audit events | Audit events are created in same transaction as operation; rolled back on API error (acceptable for test environment) |

## API Documentation

### Response Models

All endpoints use typed Pydantic response models:
- `RunSessionSummary` - Session metadata with state, timing, error info
- `RuntimeEventSummary` - Event with type, payload, actor, timing
- `CheckpointSummary` - Checkpoint with manifest details
- `ActiveCheckpointResponse` - Pointer with metadata (changed_by, changed_reason)
- `AuditEventSummary` - Audit entry with category, outcome, immutability flag

### Error Handling

Structured error responses with error_type and remediation:
- `run_not_found` (404) - Invalid run_id
- `checkpoint_not_found` (404) - Invalid checkpoint_id
- `invalid_state` (400) - Unknown state filter value
- `invalid_category` (400) - Unknown audit category filter
- `pointer_update_forbidden` (403) - Non-operator attempted update
- `pointer_rollback_forbidden` (400) - Attempted rollback to older revision

## Files Changed

```
src/api/routes/persistence.py                        (new, 800+ lines)
src/api/router.py                                     (+1 route)
src/services/workspace_checkpoint_service.py          (+75 lines, guardrails)
src/tests/integration/test_phase3_persistence_api.py  (new, 20 tests)
src/tests/integration/test_phase3_security_regressions.py (new, 15 tests)
```

## Verification Results

```bash
# Integration tests
uv run pytest src/tests/integration/test_phase3_persistence_api.py -q
# 20 passed

# Security regression tests  
uv run pytest src/tests/integration/test_phase3_security_regressions.py -q
# 15 passed

# Total: 35 tests
```

## Deviations from Plan

None - plan executed as written.

## Next Steps

This plan enables:
- **Plan 03-06**: Checkpoint restore paths and state management
- **Phase 5**: Event streaming can build on timeline APIs
- **Operational dashboards**: APIs now support run/session observability

## Artifacts

- API routes: `src/api/routes/persistence.py`
- Integration tests: `src/tests/integration/test_phase3_persistence_api.py`
- Security tests: `src/tests/integration/test_phase3_security_regressions.py`
- Service guardrails: `src/services/workspace_checkpoint_service.py`
