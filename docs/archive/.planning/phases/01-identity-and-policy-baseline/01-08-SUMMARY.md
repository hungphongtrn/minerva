---
phase: "01-identity-and-policy-baseline"
plan: "08"
subsystem: "runtime"
tags: ["policy", "egress", "tools", "default-deny", "security", "enforcement"]
dependency_graph:
  requires: ["01-04"]
  provides: ["SECU-01", "SECU-02", "gap-3-closed"]
  affects: ["phase-1-verification"]
tech_stack:
  added: []
  patterns: ["default-deny", "policy-enforcement", "deterministic-denial"]
file_tracking:
  key_files:
    created:
      - src/tests/services/test_run_policy_enforcement.py
    modified:
      - src/services/run_service.py
      - src/api/routes/runs.py
    tests:
      - src/tests/services/test_run_policy_enforcement.py
      - src/tests/runtime_policy/test_guest_and_runtime_policy.py
      - src/tests/integration/test_phase1_acceptance.py
decisions:
  - id: "D-01-08-001"
    date: "2026-02-23"
    plan: "01-08"
    decision: "Thread runtime intents through explicit fields (requested_egress_urls, requested_tools) with fallback extraction from input"
    rationale: "Allows both explicit policy intent declaration and backward-compatible input-based inference"
  - id: "D-01-08-002"
    date: "2026-02-23"
    plan: "01-08"
    decision: "Policy violation errors include action, resource, and reason in structured format"
    rationale: "Makes denials diagnosable and testable while maintaining security by not leaking sensitive policy details"
  - id: "D-01-08-003"
    date: "2026-02-23"
    plan: "01-08"
    decision: "HTTP 403 responses include parseable JSON detail with error, status, action, resource, and reason fields"
    rationale: "API consumers can programmatically handle different denial types without parsing error strings"
  - id: "D-01-08-004"
    date: "2026-02-23"
    plan: "01-08"
    decision: "Service-level tests verify real enforcement with actual RuntimeEnforcer, not mocks"
    rationale: "Prevents bypass via mocking and ensures default-deny semantics are actually enforced"
metrics:
  duration: "24 minutes"
  completed: "2026-02-23"
---

# Phase 1 Plan 08: Gap 3 Closure - Default-Deny Runtime Enforcement Summary

## Overview

Closed Gap 3 by implementing active egress and tool policy enforcement in the run execution path. Prior to this plan, the runtime policy engine and enforcer existed but were never invoked during `execute_run`. This gap meant that SECU-01 (default-deny egress) and SECU-02 (default-deny tools) were not actually enforced at execution time.

## What Was Delivered

### 1. Active Policy Enforcement in Execution Path

The `execute_run` method in `src/services/run_service.py` now:

- Accepts `requested_egress_urls` and `requested_tools` parameters
- Calls `authorize_egress` for each URL before success
- Calls `authorize_tool` for each tool before success
- Returns `status="denied"` with structured error on policy violations
- Preserves guest persistence behavior and secret filtering

### 2. Deterministic Denial Responses

Policy denials now produce consistent, parseable responses:

**Service Layer:**
- Status: `"denied"` (not `"error"`)
- Error format: `"Policy violation ({action}): {resource} - {reason}"`

**HTTP Layer:**
- Status: `403 Forbidden`
- Detail structure:
  ```json
  {
    "error": "Policy violation (egress): https://example.com - Denied by policy",
    "status": "denied",
    "action": "egress",
    "resource": "https://example.com",
    "reason": "Denied by policy"
  }
  ```

### 3. Comprehensive Regression Tests

Created `src/tests/services/test_run_policy_enforcement.py` with 23 tests covering:

- **Egress Enforcement:** Empty allowlist denies, explicit allowlist passes, wildcard patterns, multiple URLs
- **Tool Enforcement:** Empty allowlist denies, explicit allowlist passes, multiple tools
- **Deterministic Responses:** Action/resource/reason in errors, consistent status values
- **Combined Enforcement:** Egress + tool checks both enforced
- **Guest Mode:** Same enforcement applies to guest runs
- **Bypass Prevention:** Tests verify real enforcement, not mockable stubs
- **Run Result Contract:** Correct structure preservation, outputs formatting

## Key Implementation Details

### Runtime Intent Extraction

The route handler extracts runtime intents from two sources:

1. **Explicit fields:** `requested_egress_urls` and `requested_tools` (preferred for API clarity)
2. **Input inference:** Extracts `input.url` and `input.tool` for backward compatibility with existing tests

This dual approach allows gradual migration to explicit intent declaration while maintaining existing API behavior.

### Policy Check Ordering

Egress checks are performed before tool checks in `execute_run`. This means:
- If both would fail, egress denial is returned
- This ordering is consistent and deterministic
- Tests verify this ordering explicitly

### Guest Mode Enforcement

Policy enforcement applies equally to guest and authenticated runs. The only difference is persistence:
- Guest runs: Policy enforced, no persistence
- Authenticated runs: Policy enforced, persistence allowed

## Verification Results

All verification tests pass:

```bash
# Service-level enforcement tests (23 tests)
uv run pytest src/tests/services/test_run_policy_enforcement.py -q
# Result: 23 passed

# Acceptance tests for default-deny behavior (6 tests)
uv run pytest src/tests/integration/test_phase1_acceptance.py -k "DefaultDenyEgress or DefaultDenyTools" -q
# Result: 6 passed

# Existing runtime policy tests (37 tests)
uv run pytest src/tests/runtime_policy/test_guest_and_runtime_policy.py -q
# Result: 37 passed
```

## Artifacts Modified

| File | Changes |
|------|---------|
| `src/services/run_service.py` | Added `requested_egress_urls` and `requested_tools` parameters to `execute_run`. Added policy enforcement loops for egress and tools before success path. Enhanced error message format. |
| `src/api/routes/runs.py` | Added `requested_egress_urls` and `requested_tools` to `StartRunRequest`. Added runtime intent extraction from input. Updated `execute_run` call with new parameters. Enhanced denial response with structured detail. Added `action`, `resource`, and `reason` fields to `RunErrorResponse`. |
| `src/tests/services/test_run_policy_enforcement.py` | Created comprehensive test suite with 23 tests for policy enforcement. |

## Decisions Made

1. **Dual intent declaration:** Support both explicit fields and input extraction for flexibility
2. **Structured error detail:** Include action/resource/reason in HTTP response for programmability
3. **Service-level verification:** Test with real enforcer to prevent mock-based bypasses
4. **Deterministic status values:** Use `"denied"` consistently, never `"error"` for policy violations

## Must-Have Truths Verified

- [x] Run execution enforces default-deny egress policy before reporting success
- [x] Run execution enforces default-deny tool policy before reporting success
- [x] Denied egress/tool requests return deterministic policy-denied responses

## Gaps Closed

**Gap 3 - Default-Deny Enforcement:**
- **Before:** Policy models existed but were not invoked in execution path
- **After:** `execute_run` actively calls `authorize_egress` and `authorize_tool` for each request
- **Evidence:** 23 service-level tests + 6 acceptance tests all passing

## Traceability

This plan closes the following requirement gaps identified in verification:

- **SECU-01:** Runtime policy enforces default-deny egress semantics ✓
- **SECU-02:** Runtime policy enforces default-deny tool semantics ✓

## Next Steps

Gap 3 is now closed. Phase 1 verification should be re-run to confirm all 6 must-haves now pass:
- AUTH-03 (Workspace Isolation) - pending other gap closures
- AUTH-05 (Role-Based Access) - pending other gap closures  
- SECU-01 (Default-Deny Egress) - ✓ **CLOSED**
- SECU-02 (Default-Deny Tools) - ✓ **CLOSED**

## Commits

- `7676310` - feat(01-08): enforce egress and tool checks in execute_run
- `412f4a4` - feat(01-08): standardize denied response format with parseable details
- `0911f43` - test(01-08): add regression tests for default-deny enforcement
