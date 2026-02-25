---
status: closed
trigger: "Phase 02 UAT Test 4 - pack binding across profiles not verifiably wired"
created: 2026-02-25T00:00:00Z
updated: 2026-02-25T00:00:00Z
resolution: "Plans 02-09 and 02-10 completed. Provider-side pack binding implemented in both local_compose and daytona with equivalent semantics. Cross-profile parity verified by TestRegisteredPackBindingParity acceptance tests."
---

## Current Focus

Root cause identified: Agent pack binding to runtime is schema-only, not implemented end-to-end.

## Symptoms

- Expected: Registered pack runs with equivalent behavior in Local Compose and Daytona/BYOC profiles
- Actual: Profile adapter parity passes, but pack is not actually bound to runtime
- Reproduction: Phase 02 UAT Test 4

## Evidence

1. **Schema-level binding exists**: `SandboxInstance.agent_pack_id` foreign key exists (models.py:260-264)
2. **API accepts pack_id**: `run_service.py:404` and `sandbox_orchestrator_service.py:150` accept `agent_pack_id`
3. **Database stores reference**: `sandbox_orchestrator_service.py:282` stores `agent_pack_id` in DB record
4. **Config field unused**: `SandboxConfig.pack_source_path` exists (base.py:116-117) but is NEVER populated
5. **No pack retrieval**: Orchestrator never looks up pack by ID to get `source_path` for binding
6. **No runtime binding**: Provider implementations (local_compose.py, daytona.py) don't actually bind pack
7. **No E2E test**: `test_phase2_acceptance.py` has profile parity tests but no pack execution across profiles test

## Eliminated

- Provider adapter interface: Working correctly (both implement base contract)
- Database schema: Correctly supports pack binding
- API routing: Correctly accepts agent_pack_id parameter

## Resolution

root_cause: |
  Agent pack binding is implemented only at the database schema level. The agent_pack_id is stored 
  in the sandbox_instance record, but:
  1. The pack source_path is never retrieved from the AgentPack record
  2. The SandboxConfig.pack_source_path field is never populated
  3. Provider implementations don't actually bind the pack to the runtime
  4. No end-to-end test verifies pack execution works across different profiles
  
  Result: Pack registration works, pack storage works, but pack binding to runtime is not wired.

missing_items:
  - Query AgentPack by ID to get source_path in orchestrator
  - Populate SandboxConfig.pack_source_path before provisioning
  - Implement pack binding in LocalComposeSandboxProvider.provision_sandbox
  - Implement pack binding in DaytonaSandboxProvider.provision_sandbox
  - Add E2E test: register pack -> resolve sandbox with pack -> verify pack is accessible in both profiles

files_involved:
  - src/services/sandbox_orchestrator_service.py
  - src/infrastructure/sandbox/providers/local_compose.py
  - src/infrastructure/sandbox/providers/daytona.py
  - src/tests/integration/test_phase2_acceptance.py
