---
phase: "02"
plan: "11"
subsystem: "sandbox-providers"
tags: ["daytona", "sdk", "provider-adapter", "fail-closed", "pack-binding"]
dependencies:
  requires: ["02-10"]
  provides: ["SDK-backed Daytona provider", "factory configuration", "provider parity tests"]
  affects: ["03-01", "03-02"]
tech-stack:
  added: ["daytona>=0.145.0"]
  patterns: ["async-context-manager", "SDK-wrapper", "fail-closed-error-handling", "backward-compatible-constructor"]
key-files:
  created: []
  modified:
    - src/infrastructure/sandbox/providers/daytona.py
    - src/infrastructure/sandbox/providers/factory.py
    - src/config/settings.py
    - src/tests/services/test_sandbox_provider_adapters.py
    - pyproject.toml
decisions:
  - "D-02-11-001: Use AsyncDaytona with async context manager pattern for proper resource cleanup"
  - "D-02-11-002: Maintain backward-compatible constructor signatures (api_token/api_key, base_url/api_url)"
  - "D-02-11-003: Fail-closed for SDK errors: get_active_sandbox returns None on errors"
  - "D-02-11-004: Preserve pack binding metadata parity between local_compose and Daytona providers"
metrics:
  duration: "45m"
  completed: "2026-02-25"
---

# Phase 2 Plan 11: Daytona SDK-Backed Lifecycle - Summary

## One-Liner

Replaced Daytona in-memory simulation with real AsyncDaytona SDK-backed lifecycle operations while preserving semantic provider contract and pack-binding parity.

## What Was Done

### Task 1: Replace Daytona in-memory simulation with SDK-backed lifecycle operations

**Key Changes:**
- Replaced `self._sandboxes` dictionary with actual SDK calls via `AsyncDaytona`
- Implemented `provision_sandbox()` using `daytona.create(timeout=60)`
- Implemented `get_active_sandbox()` using `daytona.get()` with fail-closed error handling
- Implemented `stop_sandbox()` using `daytona.get()` + `daytona.stop()` with idempotency
- Implemented `get_health()` using `daytona.get()` with state/health mapping
- Implemented `attach_workspace()` and `update_activity()` with SDK lookups

**Semantic Contract Preservation:**
- Daytona states mapped to SandboxState: creating→HYDRATING, started/running→READY, stopping→STOPPING, stopped→STOPPED, error/failed→UNHEALTHY
- Unknown states map to UNKNOWN (fail-closed per D-02-02-002)
- Pack binding metadata (pack_bound, pack_source_path) preserved in provider metadata

**Error Handling:**
- DaytonaError caught and mapped to appropriate provider exceptions
- Fail-closed: get_active_sandbox returns None on SDK errors
- Idempotent stop: returns STOPPED state even if sandbox doesn't exist

### Task 2: Harden factory configuration for real Daytona SDK mode

**Key Changes:**
- Updated settings to support both legacy (DAYTONA_API_TOKEN) and new (DAYTONA_API_KEY) environment variables
- Self-hosted Daytona requires API key validation (fail-closed)
- Daytona Cloud mode allows implicit credential resolution via SDK
- Factory distinguishes cloud vs self-hosted via URL pattern matching

**Configuration Priority:**
1. Constructor arguments (api_key, api_url, target)
2. Legacy environment variables (DAYTONA_API_TOKEN, DAYTONA_BASE_URL, DAYTONA_TARGET_REGION)
3. New SDK environment variables (DAYTONA_API_KEY, DAYTONA_API_URL, DAYTONA_TARGET)

### Task 3: Rewrite provider adapter tests to prove real SDK call paths and parity

**New Test Classes:**
- `TestDaytonaSdkBackedProvider`: 11 tests verifying SDK method calls
- `TestDaytonaSdkBackPackBinding`: 2 tests verifying pack binding parity
- `TestDaytonaFailClosedBehavior`: 3 tests verifying fail-closed contract

**Test Coverage:**
- `test_daytona_provision_uses_sdk`: Verifies daytona.create() called with correct timeout
- `test_daytona_get_active_uses_sdk_get`: Verifies daytona.get() called with correct ref
- `test_daytona_stop_uses_sdk_stop`: Verifies daytona.stop() called appropriately
- `test_daytona_get_health_unknown_state_fails_closed`: Unknown → UNKNOWN mapping
- `test_daytona_sdk_backed_pack_binding_metadata`: pack_bound=True, pack_source_path preserved
- `test_pack_binding_noop_when_no_pack_provided_daytona`: pack_bound=False when no pack

**Mock Strategy:**
- `mock_daytona_sdk` fixture provides consistent SDK mocking
- Tests mock `AsyncDaytona` class with `__aenter__`/`__aexit__` for context manager
- Mock sandboxes have `id`, `state`, `status` attributes matching SDK response

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Constructor signature compatibility**

- **Found during:** Test execution (Task 3)
- **Issue:** Tests used `api_token` parameter but new SDK uses `api_key`
- **Fix:** Updated constructor to accept both old and new parameter names for backward compatibility
- **Files modified:** `src/infrastructure/sandbox/providers/daytona.py`
- **Commit:** c428b18

**2. [Rule 2 - Missing Critical] Environment variable backward compatibility**

- **Found during:** Task 2 implementation
- **Issue:** Existing deployments may use DAYTONA_API_TOKEN instead of DAYTONA_API_KEY
- **Fix:** Added support for both legacy and new environment variable names with priority resolution
- **Files modified:** `src/config/settings.py`, `src/infrastructure/sandbox/providers/daytona.py`
- **Commit:** c428b18

**3. [Rule 3 - Blocking] DaytonaError import path**

- **Found during:** Task 1 testing
- **Issue:** `from daytona.errors import DaytonaError` was incorrect
- **Fix:** Changed to `from daytona import DaytonaError`
- **Files modified:** `src/infrastructure/sandbox/providers/daytona.py`
- **Commit:** c428b18

## Test Results

```
uv run pytest src/tests/services/test_sandbox_provider_adapters.py -q
58 passed in 3.21s
```

### Test Categories

| Category | Count | Description |
|----------|-------|-------------|
| Factory Configuration | 7 | Profile selection, credential validation |
| Semantic Parity | 20 | Cross-provider lifecycle behavior |
| SDK-Backed Operations | 11 | Daytona SDK call verification |
| Pack Binding Parity | 4 | Metadata contract verification |
| Fail-Closed Behavior | 3 | Error handling verification |
| State Transitions | 8 | State machine correctness |
| Provider-Specific | 5 | Configuration, cloud vs self-hosted |

## Next Phase Readiness

### Ready for Phase 3

Phase 3 (Persistence and Checkpoint Recovery) can proceed with:
- Daytona provider using real SDK calls for lifecycle operations
- Deterministic factory configuration
- Provider parity tests validating cross-profile behavior
- Pack binding metadata available for routing decisions

### No Blockers

- All acceptance criteria met
- All 58 provider adapter tests passing
- SDK-backed provider ready for integration testing

## Key Technical Decisions

### D-02-11-001: AsyncDaytona Context Manager Pattern

**Decision:** Use `async with AsyncDaytona(config=config) as daytona:` pattern for all SDK operations.

**Rationale:**
- Ensures proper resource cleanup via `__aexit__`
- Follows SDK documentation best practices
- Handles connection lifecycle automatically

### D-02-11-002: Backward-Compatible Constructor

**Decision:** Support both old (`api_token`, `base_url`) and new (`api_key`, `api_url`) parameter names.

**Rationale:**
- Existing test code uses old parameter names
- Existing deployments may use old environment variables
- Smooth migration path without breaking changes

### D-02-11-003: Fail-Closed Error Handling

**Decision:** `get_active_sandbox()` returns `None` on SDK errors rather than raising exceptions.

**Rationale:**
- Aligns with semantic contract: "no active sandbox" when state unknown
- Prevents cascading failures in routing layer
- Callers can retry or provision new sandbox

### D-02-11-004: Pack Binding Metadata Preservation

**Decision:** Store `pack_bound` and `pack_source_path` in provider metadata even though Daytona SDK doesn't natively support metadata storage.

**Rationale:**
- Maintains parity with local_compose provider
- Routing layer can inspect pack binding without provider-specific code
- Future-proof: can be extended if Daytona adds metadata support

## References

- **Requirements:** WORK-02, WORK-03, WORK-05, WORK-06, AGNT-03
- **Decisions:** D-02-02-001 (Semantic State Contract), D-02-02-002 (Fail-Closed Behavior), D-02-10-001 (Provider Metadata for Pack Observability), D-02-10-002 (Equivalent but Profile-Specific Implementation)
- **Daytona SDK Docs:** https://www.daytona.io/docs/en/python-sdk/async/async-daytona/
- **Commits:**
  - c428b18: feat(02-11): replace Daytona in-memory simulation with SDK-backed lifecycle
  - 67b4542: test(02-11): harden factory configuration and rewrite SDK-backed provider tests
