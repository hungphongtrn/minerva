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
started: 2026-02-24T17:09:02Z
updated: 2026-02-24T17:16:58Z
---

## Current Test

[testing complete]

## Tests

### 1. Workspace continuity across sessions
expected: Start a run in your workspace, then start another run later with the same identity. The system reuses the same durable workspace instead of creating a new one.
result: pass

### 2. Template scaffold creates required agent files
expected: Scaffolding a new agent workspace creates AGENT.md, SOUL.md, IDENTITY.md, and a skills/ directory in the target folder.
result: pass

### 3. Agent pack registration validates before write
expected: Registering an incomplete pack returns a deterministic validation checklist and blocks registration; registering a valid pack succeeds and stores digest metadata.
result: pass

### 4. Same pack works across local and BYOC profiles
expected: The registered pack runs with equivalent behavior in Local Compose and Daytona/BYOC profile selection without manual infrastructure rewiring.
result: issue
reported: "Subagent found profile adapter parity passing, but end-to-end run-time pack binding across local_compose and daytona is not verifiably wired."
severity: major

### 5. Sandbox routing reuses healthy runtime or hydrates new
expected: If a healthy active sandbox exists for the workspace, routing reuses it; otherwise the system creates or hydrates one and attaches workspace state.
result: pass

### 6. Concurrent writes are serialized by lease
expected: Simultaneous write attempts for one workspace do not overlap; only one holder proceeds while others conflict/retry until release.
result: pass

### 7. Health and TTL controls runtime lifecycle
expected: Unhealthy sandboxes are excluded from routing, and idle sandboxes become eligible for auto-stop once TTL is exceeded.
result: pass

### 8. Isolation and guest restrictions are enforced
expected: Cross-workspace access is denied, guest mode cannot persist workspace state or register packs, and path traversal attempts are rejected.
result: pass

## Summary

total: 8
passed: 7
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Registered pack runs with equivalent behavior in Local Compose and Daytona/BYOC profile selection without manual infrastructure rewiring."
  status: failed
  reason: "Subagent reported: profile adapter parity passes, but end-to-end pack binding to runtime across profiles is not verifiably wired."
  severity: major
  test: 4
  root_cause: "Agent pack binding is only persisted in schema; runtime provisioning never resolves pack source path into SandboxConfig or provider mount/bind flow, so cross-profile execution parity for real registered packs is not guaranteed."
  artifacts:
    - path: "src/services/sandbox_orchestrator_service.py"
      issue: "Creates SandboxConfig without pack_source_path even when agent_pack_id is provided."
    - path: "src/infrastructure/sandbox/providers/local_compose.py"
      issue: "Provisioning path does not bind or mount registered pack source into runtime sandbox."
    - path: "src/infrastructure/sandbox/providers/daytona.py"
      issue: "Provisioning path does not bind or mount registered pack source into runtime sandbox."
    - path: "src/tests/integration/test_phase2_acceptance.py"
      issue: "Profile parity tests cover adapter contract but not end-to-end registered pack execution parity."
  missing:
    - "Resolve AgentPack source_path in orchestrator from agent_pack_id before provisioning."
    - "Populate SandboxConfig.pack_source_path and pass through provider provisioning path."
    - "Implement provider-side pack bind/mount behavior for local_compose and daytona adapters."
    - "Add acceptance test: register pack, run via local_compose and daytona, assert equivalent pack execution semantics."
  debug_session: ".planning/debug/phase02-pack-binding-gap.md"
