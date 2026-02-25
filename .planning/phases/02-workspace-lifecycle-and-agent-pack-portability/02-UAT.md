---
status: diagnosed
phase: 02-workspace-lifecycle-and-agent-pack-portability
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
  - 02-03-SUMMARY.md
  - 02-04-SUMMARY.md
  - 02-05-SUMMARY.md
  - 02-06-SUMMARY.md
  - 02-07-SUMMARY.md
  - 02-08-SUMMARY.md
  - 02-09-SUMMARY.md
  - 02-10-SUMMARY.md
  - 02-11-SUMMARY.md
  - 02-12-SUMMARY.md
started: 2026-02-25T00:00:00Z
updated: 2026-02-25T08:02:42Z
---

## Current Test

[testing complete]

## Tests

### 1. Workspace Continuity Across Sessions
expected: User gets same workspace ID on repeated bootstrap calls; workspace persists across sessions
result: pass

### 2. Template Scaffold Generation
expected: POST /agent-packs/scaffold creates AGENT.md, SOUL.md, IDENTITY.md files and skills/ directory in the specified path; files contain meaningful template content
result: pass

### 3. Agent Pack Registration with Validation
expected: POST /agent-packs/register validates the scaffold folder and returns either a registered pack (if valid) or a deterministic checklist with validation errors (if invalid)
result: pass

### 4. Cross-Profile Pack Execution Parity
expected: A registered agent pack runs with equivalent behavior in both local Docker Compose and Daytona profiles; same pack works without manual rewiring when switching profiles via environment
result: issue
reported: "Pack registration returned success but pack was not retrievable/listed immediately, pack-based run returned 503 while control run without agent_pack_id succeeded, and cross-profile parity to Daytona could not be exercised in the current runtime mode."
severity: major

### 5. Sandbox Routing - Active Healthy Route
expected: POST /workspaces/{id}/sandbox/resolve returns an existing healthy sandbox when one exists; response includes sandbox state (READY) and routing info
result: issue
reported: "Back-to-back resolve calls for the same workspace returned different sandbox_id values instead of reusing an existing active healthy sandbox."
severity: major

### 6. Sandbox Routing - Hydrate on Missing
expected: When no active healthy sandbox exists, resolve provisions a new sandbox and returns it with state HYDRATING→READY; workspace is attached to the new sandbox
result: pass

### 7. Concurrent Write Serialization
expected: Concurrent requests to modify the same workspace are serialized via leases; second concurrent request either waits or receives appropriate conflict response
result: issue
reported: "Concurrent same-workspace resolve requests hung until timeout (no response), and service became unresponsive afterward, indicating contention deadlock/starvation instead of safe serialization/conflict semantics."
severity: blocker

### 8. Unhealthy Sandbox Exclusion
expected: Unhealthy sandboxes are excluded from routing; resolve returns a new healthy sandbox instead of routing to an unhealthy one
result: pass

### 9. Idle TTL Auto-Stop
expected: Sandboxes automatically stop after the configured idle TTL (default 1 hour, configurable); check_stop_eligibility returns true for idle sandboxes
result: issue
reported: "TTL-expired sandbox behavior was not verifiably enforced from API+DB observation: seeded idle sandbox remained active/healthy and resolve returned changing sandbox IDs not reflected in persisted sandbox records."
severity: major

### 10. Cross-Workspace Isolation
expected: User cannot access or modify workspaces, sandboxes, or agent packs belonging to other users; API returns 403 for cross-workspace access attempts
result: pass

## Summary

total: 10
passed: 6
issues: 4
pending: 0
skipped: 0

## Gaps

- truth: "Registered pack runs with equivalent behavior in Local Compose and Daytona/BYOC profile selection without manual infrastructure rewiring"
  status: failed
  reason: "User-observed through agent test: registration succeeded but pack retrieval/listing failed, pack-based run returned 503 while control run succeeded, and Daytona parity path was not executable in current runtime mode."
  severity: major
  test: 4
  root_cause: "Pack registration is non-durable in live request flow because writes are flushed but not committed, so register can report success while subsequent list/get cannot find the pack; run path then degrades to generic 503 when pack-based routing fails; cross-profile parity is process-global via SANDBOX_PROFILE and cannot be exercised in one runtime mode without reconfiguration/restart."
  artifacts:
    - path: "src/db/session.py"
      issue: "Request DB dependency closes sessions without commit/rollback transaction handling for successful mutating requests."
    - path: "src/services/agent_pack_service.py"
      issue: "Registration relies on repository flush semantics and depends on outer commit that is missing in production request flow."
    - path: "src/services/run_service.py"
      issue: "resolve_routing_target can return success while lifecycle routing is unsuccessful, allowing execution to proceed with null/invalid routing target."
    - path: "src/api/routes/runs.py"
      issue: "Missing sandbox_id is surfaced as generic 503, masking pack-specific routing/validation failures."
    - path: "src/infrastructure/sandbox/providers/factory.py"
      issue: "Provider selection is process-global via settings.SANDBOX_PROFILE, preventing in-process local/daytona parity validation."
    - path: "src/tests/integration/conftest.py"
      issue: "Test dependency override auto-commits DB sessions, masking production no-commit behavior."
  missing:
    - "Add production transaction boundary commit/rollback handling for request sessions (or explicit commit in mutating registration flow)."
    - "Add production-equivalent integration test for register -> list/get durability without test-only auto-commit overrides."
    - "Fail fast in run routing when lifecycle/orchestrator routing is unsuccessful; do not return success with null sandbox target."
    - "Propagate pack-specific routing errors to API responses instead of generic sandbox unavailable 503."
    - "Provide deterministic profile-parity harness: request-level profile selector or scripted per-profile restart/verification path without manual rewiring."
  debug_session: ".planning/debug/phase02-test4-pack-portability-gap.md"

- truth: "Active healthy sandbox is reused for routing when available"
  status: failed
  reason: "User-observed through agent test: repeated resolve calls for the same workspace returned different sandbox_id values within seconds instead of routing to an existing active healthy sandbox."
  severity: major
  test: 5
  root_cause: "Sandbox resolution changes are flushed but not committed in request flow, so provisioned/updated sandbox records are discarded at session close; each resolve call sees no durable active sandbox and creates a new one."
  artifacts:
    - path: "src/api/routes/workspaces.py"
      issue: "resolve_sandbox route does not commit DB transaction after lifecycle resolution."
    - path: "src/services/sandbox_orchestrator_service.py"
      issue: "Provision/update path relies on caller commit; no durable transaction boundary in live flow."
    - path: "src/db/repositories/sandbox_instance_repository.py"
      issue: "Repository methods persist via flush and depend on outer commit that is missing in request handling."
    - path: "src/db/session.py"
      issue: "get_db session lifecycle closes session without success commit handling."
  missing:
    - "Add explicit commit/rollback transaction handling for mutating sandbox resolve requests."
    - "Add integration assertion that back-to-back resolve returns same sandbox_id when healthy active sandbox exists."
    - "Audit other mutating routes for same flush-without-commit persistence gap."
  debug_session: ".planning/debug/phase02-test05-sandbox-routing-reuse-gap.md"

- truth: "Concurrent same-workspace writes serialize safely via leases without deadlock"
  status: failed
  reason: "User-observed through agent test: two concurrent resolve requests timed out with no response and service became unresponsive afterward."
  severity: blocker
  test: 7
  root_cause: "Lease acquisition path under concurrent resolve requests can enter lock contention without bounded timeout/retry behavior, causing blocking that starves request handling and presents as deadlock/unresponsiveness."
  artifacts:
    - path: "src/db/repositories/workspace_lease_repository.py"
      issue: "Concurrency path lacks robust lock-conflict handling semantics in active lease acquisition under simultaneous writes."
    - path: "src/db/session.py"
      issue: "Engine/session configuration lacks explicit bounded DB lock wait safeguards for contention scenarios."
    - path: "src/services/workspace_lease_service.py"
      issue: "Acquire flow does not expose bounded timeout/backoff contract for lease contention at API level."
    - path: "src/api/routes/workspaces.py"
      issue: "Synchronous DB access within async route amplifies blocking impact during lock contention."
  missing:
    - "Implement deterministic lease contention handling with bounded timeout and conflict response semantics."
    - "Add lock wait safeguards in DB engine/session configuration for contention scenarios."
    - "Add concurrency regression test proving no hang under simultaneous same-workspace resolve requests."
  debug_session: ".planning/debug/02-phase2-test7-concurrent-lease-deadlock.md"

- truth: "Idle TTL policy auto-stops stale sandboxes and routing reflects stop eligibility"
  status: failed
  reason: "User-observed through agent test: seeded TTL-expired sandbox remained active/healthy and resolve produced non-persisted changing IDs, so TTL enforcement was not clearly observable."
  severity: major
  test: 9
  root_cause: "Idle TTL eligibility logic exists but is not wired into a durable enforcement path in live request flow; combined with missing commit durability in resolve path, TTL stop outcomes are not consistently observable from API+DB state."
  artifacts:
    - path: "src/services/sandbox_orchestrator_service.py"
      issue: "TTL eligibility/idle stop methods exist but are not reliably integrated into request-time routing enforcement path."
    - path: "src/api/routes/workspaces.py"
      issue: "resolve_sandbox route does not expose or enforce TTL cleanup lifecycle before routing response."
    - path: "src/services/sandbox_orchestrator_service.py"
      issue: "Idle cleanup methods exist but lack clear invocation mechanism in runtime control loop."
    - path: "src/api/routes/workspaces.py"
      issue: "Missing commit in resolve path undermines persistence needed to observe TTL transitions."
  missing:
    - "Integrate TTL stop-eligibility enforcement into routing flow or scheduled idle cleanup execution."
    - "Expose observable TTL cleanup status via route response or dedicated operational endpoint."
    - "Fix resolve transaction durability so TTL state transitions persist and can be validated."
    - "Add regression coverage for TTL-expired sandbox stop/replacement with persisted state assertions."
  debug_session: ".planning/debug/phase02-test09-idle-ttl-enforcement-gap.md"
