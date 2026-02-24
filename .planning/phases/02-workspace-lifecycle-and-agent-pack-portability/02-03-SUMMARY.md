---
phase: 02-workspace-lifecycle-and-agent-pack-portability
plan: 03
type: summary
subsystem: services
success: true
completed: 2026-02-24
---

# Phase 2 Plan 3: Workspace Lifecycle Services - Summary

## One-Liner
Implemented workspace lifecycle control-plane services guaranteeing continuity, safe serialization via leases, and health-aware sandbox routing with configurable idle TTL enforcement.

## What Was Built

### Workspace Lease Service (`src/services/workspace_lease_service.py`)
DB-backed lease orchestration for same-workspace write serialization:
- **Lease acquisition** with transaction-safe conflict detection and retryable CONFLICT results
- **Lease renewal/heartbeat** for long-running operations (300s default, 10s-1h range)
- **Expiration recovery** - expired leases automatically reclaimed and released
- **Fail-closed behavior** - ambiguous states result in denial rather than race conditions
- **Deterministic release** - explicit holder verification with bypass option for admin ops

### Sandbox Orchestrator Service (`src/services/sandbox_orchestrator_service.py`)
Health-aware routing and idle TTL enforcement:
- **Health-aware routing** - prefers active healthy sandboxes, excludes unhealthy from routing
- **Configurable idle TTL** - `SANDBOX_IDLE_TTL_SECONDS` (60s-24h range, default 3600s)
- **Stop eligibility** - computed from configured TTL, proves non-default values change outcomes
- **Idempotent stop** - safe to call multiple times, handles NotFound gracefully
- **Automatic provisioning** - creates replacement when no healthy candidates exist

### Workspace Lifecycle Service (`src/services/workspace_lifecycle_service.py`)
High-level orchestration entrypoint for durable workspace continuity:
- **Auto-create/reuse** - one durable workspace per user, auto-created on first use
- **Integrated lease management** - acquires lease before routing, releases in all branches
- **Health-aware sandbox resolution** - routes via orchestrator with TTL enforcement
- **LifecycleContext** - automatic cleanup helper for deterministic resource release

### Configuration Updates (`src/config/settings.py`)
- Added `SANDBOX_IDLE_TTL_SECONDS` with typed validation and docstring
- Fail-closed validation for invalid/non-positive values
- Settings-driven injection into orchestrator stop eligibility

### Service Exports (`src/services/__init__.py`)
All lifecycle services exported with their result types for downstream use.

## Key Decisions

### DEC-02-03-001: Cross-Database Lease Acquisition
**Decision**: Use explicit locking with expired lease cleanup instead of PostgreSQL-specific `on_conflict_do_nothing(where=...)`.

**Rationale**: SQLite doesn't support partial unique index constraints in upsert, and tests use SQLite. Explicit query-and-insert pattern works across both databases.

**Impact**: Repository code is portable between SQLite (tests) and PostgreSQL (production).

### DEC-02-03-002: Lease TTL Validation Range
**Decision**: Lease TTL range is 10 seconds to 1 hour (60s-24h for idle TTL).

**Rationale**: Prevents accidental immediate expiry (too short) and indefinite locks (too long). Matches operational requirements for workspace write serialization.

**Impact**: TTL values outside range raise ValueError immediately.

### DEC-02-03-003: LifecycleService as Primary Entrypoint
**Decision**: WorkspaceLifecycleService is the high-level API; lease and orchestrator services are implementation details.

**Rationale**: Routes/controllers should not coordinate lease + routing manually. Single entrypoint ensures consistent "acquire lease → route → release" pattern.

**Impact**: Future API routes call `resolve_target()` and handle the LifecycleTarget result.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Repository PostgreSQL-specific syntax failed on SQLite**
- **Found during:** Task 1 test execution
- **Issue**: `on_conflict_do_nothing(where=...)` is PostgreSQL-specific and fails on SQLite tests
- **Fix**: Replaced with explicit query-and-insert pattern with `_release_expired_leases()` and `_get_active_lease_for_update()` helpers
- **Files modified:** `src/db/repositories/workspace_lease_repository.py`
- **Verification:** 25 lease service tests pass on SQLite

## Test Results

```
$ uv run pytest src/tests/services/test_workspace_lease_service.py -q
25 passed

$ uv run pytest src/tests/services/test_sandbox_routing_service.py -q
16 passed

$ uv run pytest src/tests/services/test_workspace_lifecycle_service.py -q
18 passed

$ uv run pytest src/tests/services/test_sandbox_routing_service.py -k "ttl" -q
7 passed (includes test_non_default_ttl_changes_stop_outcome)
```

**Total: 59 service tests passing**

### Test Coverage Highlights
- Concurrent same-workspace acquire attempts serialize deterministically
- Expired lease recovery with automatic cleanup
- Non-default TTL (15 min vs 1 hour) produces different stop/no-stop outcomes
- Unhealthy sandbox exclusion triggers replacement provisioning
- Lease cleanup in both success and failure branches
- Idempotent stop operations handle already-stopped sandboxes

## Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `src/services/workspace_lease_service.py` | Created | Lease acquire/renew/release orchestration |
| `src/services/sandbox_orchestrator_service.py` | Created | Health-aware routing and idle TTL enforcement |
| `src/services/workspace_lifecycle_service.py` | Created | High-level workspace lifecycle orchestration |
| `src/services/__init__.py` | Modified | Export all lifecycle services |
| `src/config/settings.py` | Modified | Add `SANDBOX_IDLE_TTL_SECONDS` setting |
| `src/db/repositories/workspace_lease_repository.py` | Modified | Cross-database lease acquisition |
| `src/tests/services/test_workspace_lease_service.py` | Created | 25 lease service tests |
| `src/tests/services/test_sandbox_routing_service.py` | Created | 16 routing/TTL tests |
| `src/tests/services/test_workspace_lifecycle_service.py` | Created | 18 lifecycle integration tests |

## Traceability

### Requirements Addressed
- **WORK-01**: Workspace continuity across sessions - `resolve_target()` auto-creates/reuses workspace per user
- **WORK-04**: Concurrent write serialization - `WorkspaceLeaseService` with DB-backed locks
- **WORK-05**: Unhealthy sandbox exclusion - routing logic filters to healthy-only
- **WORK-06**: Idle auto-stop by TTL - `check_stop_eligibility()` with configurable TTL
- **AGNT-03**: Portability semantics - orchestrator uses provider-agnostic interface

### Provides Foundation For
- **02-04**: Template scaffold and pack registration (lifecycle service ready for pack binding)
- **02-05**: API routes (lifecycle service is the route backend)
- **02-05 SECU-05**: Security tests (lease/routing services provide testable surfaces)

## Commits

1. `d4b3be5` - feat(02-03): implement workspace lease service with acquisition, renewal, and expiration recovery
2. `e3828b4` - feat(02-03): add configurable idle TTL and sandbox orchestrator service
3. `c42b996` - feat(02-03): implement workspace lifecycle service with continuity and routing

## Next Phase Readiness

Phase 2 Plan 3 complete. Next plans in Phase 2:
- **02-04**: Template scaffold and pack registration (lifecycle service ready for integration)
- **02-05**: API routes and SECU-05 tests (services provide all backend logic)

All workspace lifecycle, lease serialization, and health-aware routing logic is deterministic and covered by focused service tests.
