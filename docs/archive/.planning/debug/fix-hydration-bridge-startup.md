---
status: resolved
trigger: "Fix sandbox hydration and bridge startup issues. Daytona sandbox is created but: 1) no DB row in sandbox_instances, 2) no Picoclaw runtime, 3) no bridge listener on port 18790, 4) wrong gateway URL construction"
created: 2026-03-04T00:00:00Z
updated: 2026-03-03T17:21:46Z
---

## Current Focus

hypothesis: Implemented fixes address provisioning drift, runtime startup gap, and gateway authority mismatch.
test: Validate with Daytona provider unit tests and routing service tests.
expecting: Passing targeted suites confirm core fixes; integration durability test may still require environment-specific follow-up.
next_action: Report resolved code changes and verification results with one follow-up integration caveat.

## Symptoms

expected: Sandbox provisioning creates sandbox_instances row, hydrates runtime, starts bridge on 18790, and returns reachable gateway URL.
actual: Daytona workspace exists but DB row missing, no runtime process, no 18790 listener, and gateway URL resolution fails.
errors: gateway-<id> DNS fails; preview URL /bridge/run returns 404.
reproduction: Provision sandbox; observe Daytona STARTED workspace without corresponding DB/runtime/bridge readiness.
started: Present in current debug session context.

## Eliminated

## Evidence

- timestamp: 2026-03-03T17:01:36Z
  checked: src/services/sandbox_orchestrator_service.py::_provision_sandbox
  found: Sandbox row is created via repository before provider provisioning; state transitions and provider_ref/gateway updates occur after provider returns.
  implication: Missing DB row is likely caused by rollback/session error path, not row creation being after Daytona create.

- timestamp: 2026-03-03T17:01:36Z
  checked: src/services/sandbox_orchestrator_service.py::_trigger_async_hydration
  found: Hydration is a stub that only flips hydration_status IN_PROGRESS->COMPLETED and does not execute runtime copy/start operations.
  implication: No runtime bridge start occurs from orchestrator hydration path.

- timestamp: 2026-03-03T17:01:36Z
  checked: src/infrastructure/sandbox/providers/daytona.py::provision_sandbox
  found: Provider writes config.json and verifies identity but does not run any explicit process to start Picoclaw bridge runtime.
  implication: Sandbox can be STARTED in Daytona while bridge port 18790 has no listener.

- timestamp: 2026-03-03T17:01:36Z
  checked: src/infrastructure/sandbox/providers/daytona.py::_derive_gateway_url_from_preview
  found: Method prepends gateway- to full preview hostname (e.g. gateway-<id>.daytona.run), producing incorrect DNS patterns.
  implication: Gateway URL construction is invalid and can explain DNS failure.

- timestamp: 2026-03-03T17:03:33Z
  checked: src/db/session.py::get_db and workspace lifecycle route flow
  found: Session commits only at request completion; any exception after provider sandbox creation rolls back DB writes while Daytona workspace remains created.
  implication: Missing sandbox_instances rows can occur as orphaned Daytona workspaces after request-level rollback.

- timestamp: 2026-03-03T17:03:33Z
  checked: src/infrastructure/sandbox/providers/daytona.py::_create_workspace_symlinks
  found: process.exec command results are not validated for non-zero exit code/stderr.
  implication: Workspace hydration commands can fail silently and still continue to "successful" provisioning path.

- timestamp: 2026-03-03T17:09:10Z
  checked: Code changes in orchestrator/provider
  found: Added early DB commit checkpoint, Daytona preview-link gateway resolution, explicit bridge startup+listener verification, hydration retry/error persistence, and orphan reconciliation helper.
  implication: Critical failure paths now preserve DB state and fail fast when runtime bootstrap is incomplete.

- timestamp: 2026-03-03T17:21:46Z
  checked: uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py -q
  found: 10 passed after adapting tests to mock runtime startup in config-only scenarios.
  implication: Daytona provisioning/config and new startup hooks are stable under unit tests.

- timestamp: 2026-03-03T17:21:46Z
  checked: uv run pytest src/tests/services/test_sandbox_routing_service.py -q
  found: 27 passed.
  implication: Orchestrator routing/provision retry behavior remains compatible with existing service tests.

- timestamp: 2026-03-03T17:21:46Z
  checked: uv run pytest src/tests/services/test_sandbox_provider_adapters.py -q -k "daytona and gateway"
  found: 2 passed after updating gateway expectations to preview-link authority and cloud unresolved-url failure mode.
  implication: Gateway URL behavior now reflects Daytona preview-based contract.

- timestamp: 2026-03-03T17:21:46Z
  checked: uv run pytest src/tests/integration/test_phase2_transaction_durability.py -q -k "resolve_persists_sandbox_durably"
  found: Failing assertion - sandbox_id returned null in this integration scenario.
  implication: Additional environment-specific investigation is needed for end-to-end integration path despite passing targeted unit/service suites.

## Resolution

root_cause: |
  Three compounded issues caused the broken flow: (1) sandbox DB writes were only request-transaction durable, allowing Daytona-created workspaces to survive while DB rows rolled back on downstream exceptions; (2) Daytona provisioning never guaranteed bridge runtime startup/listener readiness on port 18790; and (3) gateway URL derivation used invalid hardcoded hostname patterns instead of Daytona preview-link authority.
fix: |
  Updated orchestrator and Daytona provider to (a) persist sandbox creation checkpoint before provider provisioning and persist failure metadata with hydration retry counters, (b) enforce bridge startup/listener readiness checks in Daytona provisioning with strict mode when bridge is enabled, (c) resolve gateway URL via Daytona preview-link APIs, and (d) add best-effort orphan reconciliation for Daytona sandboxes labeled with workspace_id.
verification: |
  Verified via targeted tests: Daytona volume/config suite (10 passed), sandbox routing service suite (27 passed), and Daytona gateway adapter tests (2 passed). One targeted integration durability test still returns null sandbox_id and needs follow-up in integration environment.
files_changed:
  - src/services/sandbox_orchestrator_service.py
  - src/infrastructure/sandbox/providers/daytona.py
  - src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py
  - src/tests/services/test_sandbox_provider_adapters.py
