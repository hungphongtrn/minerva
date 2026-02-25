---
phase: 02-workspace-lifecycle-and-agent-pack-portability
verified: 2026-02-25T09:08:47Z
status: gaps_found
score: 10/11 must-haves verified
re_verification:
  previous_status: human_needed
  previous_score: 11/11
  gaps_closed: []
  gaps_remaining:
    - "Real BYOC profile parity run is failing for daytona on valid-pack routing path"
  regressions:
    - "Cross-profile parity truth regressed from pending-human to failed after real BYOC evidence"
gaps:
  - truth: "A registered valid agent pack runs with equivalent semantics across local_compose and daytona BYOC profiles"
    status: failed
    reason: "Real parity evidence shows profile divergence: local profile passes run-routing suite, daytona profile returns HTTP 400 for valid-pack run path where local does not"
    artifacts:
      - path: "src/scripts/phase2_profile_parity_harness.py"
        issue: "Harness reports overall FAIL with local PASS and daytona FAIL in CI mode under .env-backed credentials"
      - path: "src/tests/integration/test_phase2_run_routing_errors.py"
        issue: "`TestFailFastRouting.test_run_does_not_fail_with_pack_error_for_valid_pack` fails under daytona profile (expected [201,503,500], got 400)"
      - path: "src/api/routes/runs.py"
        issue: "Run endpoint still emits a 400-class routing result for valid pack in daytona runtime path, violating parity outcome contract"
    missing:
      - "Fix daytona valid-pack routing path so successful/infra-failure outcomes match local semantics (no 400 pack/routing client error for valid pack)"
      - "Add/adjust deterministic test coverage proving valid-pack response parity across local_compose and daytona with real credentials"
      - "Re-run parity harness in CI mode with .env credentials and capture PASS for both profiles"
---

# Phase 2: Workspace Lifecycle and Agent Pack Portability Verification Report

**Phase Goal:** Each user gets a durable workspace and can move from template scaffold to registered agent pack that runs in local Docker Compose and BYOC profiles without manual infra wiring.
**Verified:** 2026-02-25T09:08:47Z
**Status:** gaps_found
**Re-verification:** Yes - after human-run parity evidence

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User workspace is durable and reused across sessions | ✓ VERIFIED | Workspace lifecycle reuse path remains implemented and covered (`src/services/workspace_lifecycle_service.py:255`, `src/tests/integration/test_phase2_acceptance.py:60`). |
| 2 | User can scaffold required template artifacts and register an agent pack | ✓ VERIFIED | Scaffold + register routes/services remain substantive and wired (`src/services/agent_scaffold_service.py:53`, `src/api/routes/agent_packs.py:174`, `src/api/routes/agent_packs.py:287`). |
| 3 | Routing prefers healthy active sandbox and provisions replacement otherwise | ✓ VERIFIED | Resolve path still routes through orchestrator selection/provisioning (`src/services/sandbox_orchestrator_service.py:205`, `src/services/sandbox_orchestrator_service.py:232`). |
| 4 | Lease serialization, unhealthy exclusion, and TTL policy are enforced | ✓ VERIFIED | Lease gating and TTL request-path cleanup remain in code and tests (`src/services/workspace_lifecycle_service.py:169`, `src/services/sandbox_orchestrator_service.py:189`). |
| 5 | Daytona provider is SDK-backed and fail-closed | ✓ VERIFIED | Daytona provider uses `AsyncDaytona` and fail-closed handling (`src/infrastructure/sandbox/providers/daytona.py:18`, `src/infrastructure/sandbox/providers/daytona.py:285`). |
| 6 | 02-13 durability behavior persists across request boundaries | ✓ VERIFIED | Request-scoped commit/rollback remains wired in DB dependency and integration override (`src/db/session.py:93`, `src/tests/integration/conftest.py:77`). |
| 7 | 02-13 resolve path reuses healthy sandbox rather than ID churn | ✓ VERIFIED | Reuse assertions remain in durability integration tests (`src/tests/integration/test_phase2_transaction_durability.py:266`). |
| 8 | 02-14 pack-based run routing preserves deterministic fail-fast contract | ✓ VERIFIED | Error typing/map implementation remains present and wired (`src/services/run_service.py:492`, `src/api/routes/runs.py:162`, `src/api/routes/runs.py:274`). |
| 9 | 02-15 lease contention is bounded, retryable, and service remains responsive | ✓ VERIFIED | Lease retry/lock-conflict contract remains implemented (`src/services/workspace_lease_service.py:194`, `src/db/repositories/workspace_lease_repository.py:101`). |
| 10 | 02-16 TTL-expired sandboxes are stopped before routing and exposed in API output | ✓ VERIFIED | TTL cleanup metadata still propagated to resolve response (`src/services/sandbox_orchestrator_service.py:190`, `src/api/routes/workspaces.py:320`). |
| 11 | Registered valid pack runs with equivalent semantics in local_compose and daytona BYOC | ✗ FAILED | New real parity run with `.env` credentials fails daytona path: harness `--mode ci` => overall FAIL (local PASS/daytona FAIL); direct profile test run shows `SANDBOX_PROFILE=daytona` has 1 failing test (`test_run_does_not_fail_with_pack_error_for_valid_pack`) returning 400 instead of [201,503,500], while local profile is 13/13 passing. |

**Score:** 10/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/services/run_service.py` | Fail-fast routing contract with typed routing errors | ✓ VERIFIED | Exists (587 lines), substantive, returns typed `routing_error_type` for route mapping (`src/services/run_service.py:499`). |
| `src/api/routes/runs.py` | Deterministic HTTP mapping for routing errors | ⚠️ PARTIAL | Exists (381 lines), substantive and wired, but real daytona valid-pack runtime currently produces a 400 outcome that breaks parity expectation. |
| `src/scripts/phase2_profile_parity_harness.py` | Automatable local/daytona parity verification workflow | ✓ VERIFIED | Exists (424 lines), substantive, runs both profiles under `SANDBOX_PROFILE` in CI mode (`src/scripts/phase2_profile_parity_harness.py:282`, `src/scripts/phase2_profile_parity_harness.py:295`). |
| `src/tests/integration/test_phase2_run_routing_errors.py` | Regression coverage for fail-fast and profile parity semantics | ✓ VERIFIED | Exists (415 lines), substantive, includes explicit valid-pack non-400 assertion (`src/tests/integration/test_phase2_run_routing_errors.py:242`). |
| `src/infrastructure/sandbox/providers/daytona.py` | SDK-backed Daytona lifecycle adapter | ✓ VERIFIED | Exists (580 lines), substantive, uses real SDK context for get/create/health/stop (`src/infrastructure/sandbox/providers/daytona.py:254`, `src/infrastructure/sandbox/providers/daytona.py:314`). |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `src/scripts/phase2_profile_parity_harness.py` | `src/tests/integration/test_phase2_run_routing_errors.py` | Profile-switched pytest subprocess (`SANDBOX_PROFILE`) | ✓ WIRED | Harness executes same test file in local/daytona (`src/scripts/phase2_profile_parity_harness.py:149`, `src/scripts/phase2_profile_parity_harness.py:156`). |
| `src/api/routes/runs.py` | `src/services/run_service.py` | `execute_with_routing` + `_map_routing_error` | ✓ WIRED | Route maps service routing error types into deterministic HTTP responses (`src/api/routes/runs.py:142`, `src/api/routes/runs.py:163`). |
| `src/services/run_service.py` | `src/services/workspace_lifecycle_service.py` | `resolve_target(...)` | ✓ WIRED | Run service gates execution on lifecycle routing success (`src/services/run_service.py:364`, `src/services/run_service.py:492`). |
| Real daytona runtime | Valid-pack run API contract | `POST /api/v1/runs` with `agent_pack_id` | ✗ NOT_WIRED (behavioral) | Human-run evidence shows daytona emits 400 for valid pack path where parity contract expects non-400 outcome. |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
| --- | --- | --- |
| AGNT-01 | ✓ SATISFIED | None |
| AGNT-02 | ✓ SATISFIED | None |
| AGNT-03 | ✗ BLOCKED | Cross-profile runtime parity is failing in real daytona execution (valid-pack run path returns 400). |
| WORK-01 | ✓ SATISFIED | None |
| WORK-02 | ✓ SATISFIED | None |
| WORK-03 | ✓ SATISFIED | None |
| WORK-04 | ✓ SATISFIED | None |
| WORK-05 | ✓ SATISFIED | None |
| WORK-06 | ✓ SATISFIED | None |
| SECU-05 | ✓ SATISFIED | None |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/api/routes/runs.py` | 255 | Placeholder comment in `get_run` endpoint | ⚠️ Warning | Not a direct blocker for Phase 2 goal, but indicates unfinished non-critical endpoint behavior. |
| `src/services/run_service.py` | 258 | Placeholder execution note in `execute_run` docstring | ℹ️ Info | Full execution engine deferred to later phases; routing contract is the relevant Phase 2 scope. |
| Runtime evidence (daytona profile) | N/A | Valid-pack run returns 400 in parity test | 🛑 Blocker | Breaks required local/daytona parity for registered pack execution. |

### Gaps Summary

Phase 2 remains structurally implemented, but the new real parity evidence converts the prior human-only uncertainty into a concrete blocker: daytona profile does not preserve valid-pack run outcome parity with local profile. Because the phase goal explicitly requires portability across local Docker Compose and BYOC profiles without manual rewiring, this runtime divergence is a must-have failure and blocks full goal achievement.

---

_Verified: 2026-02-25T09:08:47Z_
_Verifier: OpenCode (gsd-verifier)_
