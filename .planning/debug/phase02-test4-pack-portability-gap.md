---
status: diagnosed
trigger: "Retry diagnosis for UAT gap from Phase 02 Test 4.\n\nContext:\n- Project: /Users/phong/Workspace/minerva\n- UAT: .planning/phases/02-workspace-lifecycle-and-agent-pack-portability/02-UAT.md\n- Failed truth: Registered pack runs with equivalent behavior in Local Compose and Daytona without manual rewiring.\n- Observed during UAT: register returned success but pack not retrievable/listed; pack-based run returned 503 while control run without agent_pack_id succeeded; cross-profile parity not executable in current runtime mode.\n\nTask:\n1) Diagnose root cause(s) in code (services/routes/repositories/config/runtime behavior).\n2) Identify concrete artifacts (file path + issue).\n3) List missing fixes required to close this gap.\n4) Provide debug session path under .planning/debug/.\n\nConstraints:\n- Research only, no code edits.\n- Return exact format:\nroot_cause: ...\nartifacts:\n  - path: ...\n    issue: ...\nmissing:\n  - ...\ndebug_session: ..."
created: 2026-02-25T07:56:36Z
updated: 2026-02-25T07:58:34Z
---

## Current Focus

hypothesis: Root causes confirmed in persistence, error propagation, and runtime profile selection boundaries.
test: Synthesize findings into concrete artifacts and missing fixes for UAT Test 4 gap closure.
expecting: Diagnosis clearly maps each observed symptom to a code-level mechanism.
next_action: return diagnosis in requested structure

## Symptoms

expected: Registered pack is retrievable/listed and runs equivalently in Local Compose and Daytona without manual rewiring.
actual: Register reported success but pack not retrievable/listed; pack-based run returned 503 while control run without agent_pack_id succeeded; cross-profile parity not executable in current runtime mode.
errors: 503 on pack-based run with agent_pack_id.
reproduction: Execute Phase 02 Test 4 UAT flow (register pack, list/get pack, run using agent_pack_id under local compose and Daytona parity checks).
started: Observed during Phase 02 Test 4 UAT.

## Eliminated

## Evidence

- timestamp: 2026-02-25T07:56:50Z
  checked: UAT gap definition and repository file map
  found: UAT test 4 reports register success + non-retrievable/listed pack + 503 only on pack-bound run; codebase has dedicated agent pack route/service/repository and profile-specific parity tests.
  implication: Root cause likely spans persistence/read path and runtime execution path rather than a single endpoint typo.

- timestamp: 2026-02-25T07:57:59Z
  checked: src/api/routes/agent_packs.py, src/services/agent_pack_service.py, src/db/repositories/agent_pack_repository.py, src/db/session.py
  found: register path only flushes via repository/service; route never commits; default get_db dependency yields session and only closes it (no commit/rollback orchestration).
  implication: Register can return success within request transaction but data is not durable for next request, matching "registered but not retrievable/listed" symptom.

- timestamp: 2026-02-25T07:57:59Z
  checked: src/services/sandbox_orchestrator_service.py, src/services/workspace_lifecycle_service.py, src/services/run_service.py, src/api/routes/runs.py
  found: with agent_pack_id, orchestrator validates pack existence; missing/invalid pack returns failed routing; run service still reports routing success with sandbox_id None; runs route converts missing sandbox_id into 503.
  implication: Non-pack control run can succeed while pack-bound run returns 503, and the 503 message masks underlying pack lookup/validation failure.

- timestamp: 2026-02-25T07:58:34Z
  checked: src/tests/integration/conftest.py and profile wiring in runtime services/factory
  found: tests override get_db and commit on successful requests, masking production no-commit behavior; runtime routing has no request-level profile selector and provider is instantiated from global SANDBOX_PROFILE, so cross-profile parity cannot be exercised in one running mode without restarting/reconfiguring runtime.
  implication: Existing tests can pass while real runtime fails persistence, and parity UAT is blocked by environment/profile coupling rather than per-request profile execution.

## Resolution

root_cause: Registration writes are not committed in the production request path, so packs appear successfully registered in-request but are not durable for subsequent list/get or pack-bound runs. When pack-bound routing fails (e.g., pack lookup misses), run routing still reports success and the API surfaces a generic 503 from missing sandbox_id, masking the underlying pack error. Additionally, runtime profile choice is process-global (SANDBOX_PROFILE) with no request-level switch, so cross-profile parity is not executable within a single runtime mode.
fix: Add request transaction commit/rollback handling in live get_db path (or explicit commit in mutating routes/services); propagate routing failure from lifecycle/orchestrator through RunService as failure (not success with empty sandbox); expose/enable deterministic profile switching strategy for parity execution (explicit request/profile parameter or controlled runtime restart harness).
verification: 
files_changed: []
