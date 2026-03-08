---
status: resolved
trigger: "Investigate issue: sandbox-creation-hanging"
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T08:44:00Z
---

## Current Focus

hypothesis: Provisioning failures are caused by premature identity gate failure (sandbox still creating), retrying provider create multiple times, and missing timeout/metadata handling.
test: Verification complete via focused test suites and regression cases.
expecting: N/A
next_action: Archive resolved debug session.

## Symptoms

expected: User sends message, sandbox provisions (creating -> active), returns within 30s with gateway URL accessible.
actual: Request times out after 60s, sandbox stuck in creating state, provider_ref and gateway_url remain null, no Daytona SDK completion logging.
errors: Multiple "Unclosed client session" and "Unclosed connector" warnings from aiohttp.
reproduction: Send first message to trigger sandbox creation via Alice session.
started: Worked for infrastructure/migrations/server startup; fails at first user message sandbox creation.

## Eliminated

## Evidence

- timestamp: 2026-03-03T08:11:00Z
  checked: src/services/sandbox_orchestrator_service.py `_provision_sandbox`
  found: DB record is set to `creating` before provider call, and transitions to `active` only after `provider_info = await self._provider.provision_sandbox(config)` returns.
  implication: Any hang in provider call leaves `provider_ref` and `gateway_url` null with state stuck at `creating`.

- timestamp: 2026-03-03T08:12:00Z
  checked: src/infrastructure/sandbox/providers/daytona.py `provision_sandbox`
  found: `await daytona.create(create_params)` is awaited with no outer timeout guard; subsequent identity/gateway steps are synchronous in same request path.
  implication: Slow/hanging create blocks request until upstream timeout and prevents DB updates.

- timestamp: 2026-03-03T08:13:00Z
  checked: src/infrastructure/sandbox/providers/daytona.py return payload
  found: Gateway URL is resolved but never inserted into `provider_info.ref.metadata`; orchestrator expects `provider_info.ref.metadata["gateway_url"]`.
  implication: Even successful provisioning can leave DB `gateway_url` null for Daytona profile.

- timestamp: 2026-03-03T08:14:00Z
  checked: src/db/models.py SandboxInstance schema
  found: `provider_ref` and `gateway_url` are nullable and only set post-provision in orchestrator.
  implication: Null fields are consistent with provider call never returning.

- timestamp: 2026-03-03T08:17:00Z
  checked: src/services/daytona_pack_volume_service.py and src/scripts/daytona_base_image_preflight.py
  found: Same SDK call form `await daytona.create(...)` is used elsewhere; preflight script wraps create in `asyncio.wait_for` timeout.
  implication: `create()` is intended async API; missing timeout guard in provider is a likely hang amplifier.

- timestamp: 2026-03-03T08:22:00Z
  checked: `uv run python` SDK introspection
  found: `AsyncDaytona.create` is coroutine function with signature `(params=None, *, timeout=60, ...)`.
  implication: `create()` is truly async; hanging is not due to using a sync API, but due to lifecycle/timeout behavior around it.

- timestamp: 2026-03-03T08:24:00Z
  checked: `verify_identity_files` state gating logic
  found: method returns immediate failure when state is not running/started instead of polling until timeout.
  implication: newly created sandboxes in `creating` can fail identity gate prematurely, causing retries and duplicate Daytona artifacts with one DB row.

- timestamp: 2026-03-03T08:35:00Z
  checked: focused pytest execution
  found: `src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py` and `src/tests/services/test_sandbox_routing_service.py` both pass after provider patch.
  implication: fix does not break existing Daytona config/routing behavior; regression tests still needed for newly fixed edge case.

- timestamp: 2026-03-03T08:43:00Z
  checked: focused pytest re-run with new regression tests
  found: 36 tests passed across Daytona provider + routing suites, including new creating->started polling and gateway metadata tests.
  implication: root-cause fix is validated and guarded against regression.

## Resolution

root_cause:
  Premature identity verification failure in Daytona provider: `verify_identity_files()` fails immediately when sandbox state is `creating`, causing provisioning retries that create extra Daytona resources while the DB row remains in `creating`. Additionally, provider create call has no explicit timeout guard and returned metadata omits `gateway_url`, preventing orchestrator persistence.
fix:
  Updated `src/infrastructure/sandbox/providers/daytona.py` to (1) poll sandbox state in `verify_identity_files()` instead of failing immediately on non-running states, (2) enforce explicit create timeout around `daytona.create(...)` with `asyncio.wait_for`, and (3) merge `gateway_url` and identity metadata into returned `SandboxInfo.ref.metadata` for orchestrator persistence.
  Added regression tests in `src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py` for creating->started identity polling and gateway URL metadata propagation.
verification:
  Verified with `uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py src/tests/services/test_sandbox_routing_service.py` (36 passed). New tests confirm identity verification waits for running state and gateway URL is propagated to orchestrator metadata.
files_changed:
  - src/infrastructure/sandbox/providers/daytona.py
  - src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py
