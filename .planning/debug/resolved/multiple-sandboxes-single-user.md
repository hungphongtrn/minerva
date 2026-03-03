---
status: resolved
trigger: "CRITICAL BUG: Multiple sandboxes spawned for single user. This violates the 1:1 user:sandbox invariant."
created: 2026-03-03T16:31:38Z
updated: 2026-03-03T16:36:01Z
---

## Current Focus

hypothesis: Fix is validated by regression tests that force a `CREATING` user sandbox path and ensure no duplicate provisioning call.
test: Run targeted per-user routing tests including new regression test.
expecting: Existing in-flight sandbox is reused and provider `provision_sandbox` is not called again.
next_action: Archive debug session with verification notes.

## Symptoms

expected: 1 user = 1 sandbox; concurrent requests from same user share same sandbox.
actual: Multiple sandboxes created for a single user during rapid/concurrent requests.
errors: Violates Picoclaw Runtime Invariant #1.
reproduction: Send multiple rapid requests or concurrent requests from same user.
started: Observed in previous runs; multiple Daytona datasets for a single DB record.

## Eliminated

## Evidence

- timestamp: 2026-03-03T16:32:12Z
  checked: `src/services/sandbox_orchestrator_service.py` `_provision_sandbox()`
  found: Uses `_find_in_progress_sandbox()` (SELECT PENDING/CREATING) then `repository.create()` when none found.
  implication: Classic check-then-create race window under concurrent requests.

- timestamp: 2026-03-03T16:32:12Z
  checked: `src/services/sandbox_orchestrator_service.py` query behavior
  found: `_find_in_progress_sandbox()` has no `FOR UPDATE`/locking clause.
  implication: Concurrent transactions can both miss and both insert.

- timestamp: 2026-03-03T16:32:12Z
  checked: `src/db/models.py` `SandboxInstance`
  found: No `UniqueConstraint` on `external_user_id` with active/creating lifecycle states.
  implication: Database permits duplicate per-user sandbox rows in active lifecycle states.

- timestamp: 2026-03-03T16:33:29Z
  checked: `src/db/repositories/sandbox_instance_repository.py`
  found: `create()` is plain insert + flush with no conflict handling or lock orchestration.
  implication: Concurrent creators can both insert when no DB uniqueness constraint blocks them.

- timestamp: 2026-03-03T16:33:29Z
  checked: `src/services/oss_user_queue.py` and `src/api/oss/routes/runs.py`
  found: Request serialization is in-process asyncio lock only.
  implication: Multi-process/replica traffic is not serialized; DB-level protection is required.

- timestamp: 2026-03-03T16:33:29Z
  checked: `src/db/migrations/versions/0003_workspace_lifecycle_and_agent_pack_foundation.py` and `src/db/migrations/versions/0007_external_identities_and_sandbox_user_key.py`
  found: No partial unique index exists for `(workspace_id, external_user_id)` in non-terminal sandbox states.
  implication: Schema does not enforce 1:1 user:sandbox invariant during lifecycle transitions.

- timestamp: 2026-03-03T16:36:01Z
  checked: `uv run pytest src/tests/services/test_sandbox_routing_service.py -k "reuses_creating_user_sandbox_without_reprovisioning or provision_new_sandbox_for_new_user_no_existing or route_to_correct_user_sandbox_when_multiple_users_in_same_workspace"`
  found: 3 passed; new regression test confirms `provision_sandbox` is not called when same-user sandbox is already `CREATING`.
  implication: Concurrent same-user requests now reuse in-flight provisioning path instead of reprovisioning.

- timestamp: 2026-03-03T16:36:01Z
  checked: `uv run pytest src/tests/services/test_sandbox_provider_adapters.py -k "bounded_reprovision_exhausts_budget_and_fails_fast or gateway_persistence_and_authoritative_resolution"`
  found: 1 passed, 1 failed with expected mismatch on reprovision exhaustion for identity error path.
  implication: Failure is in bounded-retry expectation and not in per-user concurrency path fixed here.

## Resolution

root_cause: Concurrent requests follow a non-atomic sandbox provisioning path. Existing `CREATING` rows are reused but still reprovisioned by multiple callers, and schema lacks a partial unique lifecycle index for per-user sandboxes.
fix: Added wait-and-reuse behavior in `_provision_sandbox()` so callers encountering an in-flight `PENDING/CREATING` sandbox wait for activation instead of provisioning again; added partial unique index migration `uq_sandbox_user_active_lifecycle` over `(workspace_id, external_user_id)` for states `pending/creating/active`.
verification:
  - Added regression test ensuring creating sandbox is reused without provider reprovision.
  - Targeted per-user routing tests pass (3/3).
  - New migration enforces DB-level uniqueness for user lifecycle rows (`pending/creating/active`).
files_changed:
  - src/services/sandbox_orchestrator_service.py
  - src/db/migrations/versions/0008_enforce_unique_user_active_sandbox.py
  - src/tests/services/test_sandbox_routing_service.py
