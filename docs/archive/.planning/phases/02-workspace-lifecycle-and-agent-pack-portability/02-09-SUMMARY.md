---
phase: 02-workspace-lifecycle-and-agent-pack-portability
plan: 09
type: summary
subsystem: services
success: true
completed: 2026-02-25
---

# Phase 2 Plan 9: Agent Pack Runtime Wiring - Summary

## One-Liner
Closed the core runtime wiring gap by propagating `agent_pack_id` from run requests through lifecycle services to sandbox orchestrator provisioning, with fail-closed validation that resolves pack `source_path` into `SandboxConfig.pack_source_path`.

## What Was Built

### Task 1: Agent Pack ID Propagation
**Files Modified:**
- `src/services/run_service.py` - Added `agent_pack_id` parameter to `resolve_routing_target()` and pass it through from `execute_with_routing()`
- `src/services/workspace_lifecycle_service.py` - Added `agent_pack_id` parameter to `resolve_target()` and `_resolve_sandbox()`, converts string to UUID at service boundary

**Key Design Decisions:**
- UUID conversion happens at lifecycle service boundary for type safety
- Invalid UUID format returns graceful error without crashing
- Maintains backward compatibility - all pack parameters are optional

### Task 2: Pack Source Path Resolution with Fail-Closed Validation
**File Modified:** `src/services/sandbox_orchestrator_service.py`

**Capabilities Added:**
- Resolves AgentPack by ID using AgentPackRepository before provisioning
- Validates pack exists (fail-closed: PROVISION_FAILED if missing)
- Validates pack belongs to requesting workspace (prevents cross-workspace binding)
- Validates pack is active (inactive packs rejected)
- Validates pack status is VALID (pending/invalid/stale packs rejected)
- Populates `SandboxConfig.pack_source_path` with resolved pack source path
- No provider provisioning call occurs if any validation fails

**Fail-Closed Guarantees:**
| Validation | Failure Mode | Provider Called |
|------------|--------------|-----------------|
| Pack not found | PROVISION_FAILED with "not found" message | No |
| Cross-workspace pack | PROVISION_FAILED with ownership error | No |
| Inactive pack | PROVISION_FAILED with "not active" message | No |
| Invalid status | PROVISION_FAILED with status message | No |
| All pass | PROVISIONED_NEW with pack_source_path set | Yes |

### Task 3: Service-Level Tests
**Files Modified:**
- `src/tests/services/test_workspace_lifecycle_service.py` - Added `test_resolve_target_passes_agent_pack_id_to_orchestrator`
- `src/tests/services/test_sandbox_routing_service.py` - Added 5 new tests:
  - `test_resolve_sandbox_populates_pack_source_path_from_agent_pack_id`
  - `test_resolve_sandbox_rejects_cross_workspace_agent_pack_binding`
  - `test_resolve_sandbox_rejects_missing_agent_pack`
  - `test_resolve_sandbox_rejects_inactive_agent_pack`
  - `test_resolve_sandbox_rejects_invalid_agent_pack_status`

## Key Decisions

### DEC-02-09-001: Service Boundary UUID Conversion
**Decision:** Convert string `agent_pack_id` to UUID in lifecycle service before passing to orchestrator.

**Rationale:** Type safety at internal boundaries prevents format errors deeper in the stack; orchestrator can assume UUID type.

### DEC-02-09-002: Fail-Closed Validation Before Provisioning
**Decision:** All pack validations occur before any provider provisioning call.

**Rationale:** Security and cost - fail fast before expensive/side-effectful operations; no orphaned sandboxes on validation failure.

### DEC-02-09-003: SQLite String Enum Handling
**Decision:** Handle AgentPackValidationStatus as string constants (not Python enum) for SQLite compatibility.

**Rationale:** Status is stored as strings in SQLite; using `.value` attribute caused AttributeError.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AgentPackValidationStatus comparison used .value on strings**
- **Found during:** Task 3 test execution
- **Issue:** `AgentPackValidationStatus` is a class with string constants, not a Python enum; accessing `.value` raised AttributeError in SQLite
- **Fix:** Changed comparison to use direct string comparison
- **Files modified:** `src/services/sandbox_orchestrator_service.py`

## Test Results

### Verification Command
```bash
uv run pytest src/tests/services/test_workspace_lifecycle_service.py src/tests/services/test_sandbox_routing_service.py -k "agent_pack_id or pack_source_path" -q
```

### Results
```
2 passed
```

### Full Test Suite
```bash
uv run pytest src/tests/services/test_workspace_lifecycle_service.py src/tests/services/test_sandbox_routing_service.py -q
```

**Results:** 40 passed, 0 failed

### Test Coverage
- **Propagation test (1):** Verifies agent_pack_id flows through lifecycle to orchestrator
- **Source path test (1):** Verifies pack_source_path is resolved and passed to provider config
- **Fail-closed tests (4):** Cross-workspace, missing, inactive, and invalid status all rejected

## Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `src/services/run_service.py` | Modified | Propagate agent_pack_id to lifecycle |
| `src/services/workspace_lifecycle_service.py` | Modified | Accept and forward agent_pack_id, convert to UUID |
| `src/services/sandbox_orchestrator_service.py` | Modified | Resolve pack, validate, populate pack_source_path |
| `src/tests/services/test_workspace_lifecycle_service.py` | Modified | Add propagation test |
| `src/tests/services/test_sandbox_routing_service.py` | Modified | Add source path and validation tests |

## Traceability

### Requirements Addressed
- **AGNT-03**: Portability semantics - pack source path now flows to provider for mounting
- **WORK-01**: Workspace continuity - pack binding maintained across sessions via source_path
- **SECU-05**: Isolation boundaries - cross-workspace pack binding blocked

### Closes UAT Gap
- **Test 4 Gap:** "Registered pack runs with equivalent behavior across profiles" - now service-layer wired; provider mount implementation in next plan

### Provides Foundation For
- Provider-specific pack mounting (local_compose, daytona)
- End-to-end pack execution parity tests across profiles

## Commits

1. `9a699a6` - feat(02-09): propagate agent_pack_id through run and lifecycle orchestration
2. `bb45c7e` - feat(02-09): resolve pack source path in orchestrator with fail-closed validation
3. `2eb7808` - test(02-09): add service tests for agent pack propagation and validation
4. `e7c09b4` - fix(02-09): correct AgentPackValidationStatus comparison for string constants
5. `8b2c01a` - test(02-09): update test to compare UUID instead of string

## Next Phase Readiness

Plan 02-09 complete. The service wiring now:
1. ✓ Carries `agent_pack_id` from run request to provisioning
2. ✓ Resolves and validates pack before provider call
3. ✓ Populates `SandboxConfig.pack_source_path` for provider use
4. ✓ Fails closed on any invalid pack binding attempt

**Remaining for full Test 4 closure:**
- Provider-specific pack mounting implementation (local_compose.py, daytona.py)
- End-to-end acceptance test verifying pack execution across profiles

---
*Gap closure complete - runtime wiring from request to orchestrator now deterministic and fail-closed*
