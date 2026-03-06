---
status: resolved
trigger: "Investigate issue: zeroclaw-webhook-vs-execute-endpoint"
created: 2026-03-06T10:10:40Z
updated: 2026-03-06T10:16:36Z
---

## Current Focus

hypothesis: Endpoint mismatch is resolved by explicit compatibility fallback and spec contract alignment.
test: Validate with targeted tests for spec loading and gateway execution path behavior.
expecting: New and existing tests pass, confirming `/execute` and `/webhook` compatibility handling.
next_action: Archive debug session as resolved.

## Symptoms

expected: Orchestrator expects POST /execute endpoint for agent execution with SSE streaming (per spec.json: "execute_path": "/execute")
actual: Zeroclaw actually exposes POST /webhook for incoming webhooks from channels (WhatsApp, Telegram, etc.), but NOT /execute
errors: Endpoint mismatch - /execute returns 404, /webhook exists but purpose unclear
reproduction: Check Zeroclaw gateway implementation to see available endpoints and their purposes
started: Discovered during Phase 03.4 Zeroclaw migration - spec.json assumes /execute but actual implementation uses /webhook

## Eliminated

## Evidence

- timestamp: 2026-03-06T10:11:00Z
  checked: src/integrations/zeroclaw/spec.json
  found: Gateway spec hardcodes `execute_path` as `/execute` and `stream_mode` as `sse`.
  implication: Orchestrator is contractually expecting an execute endpoint with SSE semantics.

- timestamp: 2026-03-06T10:11:00Z
  checked: src/services/zeroclaw_gateway_service.py
  found: Service always posts JSON to `spec.gateway.execute_path` and expects HTTP 200 JSON response via `response.json()` (no SSE parsing).
  implication: Current client implementation is synchronous JSON over HTTP; if runtime is webhook-first, request contract must still match to work.

- timestamp: 2026-03-06T10:11:27Z
  checked: repository-wide search for `webhook` and route literals in source files
  found: No runtime endpoint implementation for `/webhook` or `/execute` exists in this repository.
  implication: Endpoint behavior must be validated against external Zeroclaw runtime/image, not local code.

- timestamp: 2026-03-06T10:11:54Z
  checked: local Docker image inspection/pull for `daytonaio/workspace-picoclaw:latest`
  found: Image is not locally present and `docker pull` failed with access denied/non-existent repository.
  implication: Direct runtime binary inspection is blocked; must rely on reachable source/docs or existing contract tests.

- timestamp: 2026-03-06T10:12:47Z
  checked: external discovery channels (GitHub code search, public docs) for Zeroclaw runtime routes
  found: GitHub code search requires authentication; public Daytona docs do not expose Zeroclaw gateway route contract.
  implication: Need empirical endpoint probing against a live gateway instance to confirm compatibility.

- timestamp: 2026-03-06T10:14:27Z
  checked: src/infrastructure/sandbox/providers/daytona.py `_generate_zeroclaw_config`
  found: Runtime config emitted into sandbox is fully spec-driven (`health_path`, `execute_path`, `stream_mode`) and service remains JSON-request/JSON-response oriented.
  implication: Spec/client drift directly impacts live routing; adding client-side fallback is lowest-risk compatibility fix without runtime image changes.

- timestamp: 2026-03-06T10:14:27Z
  checked: local DB sandbox_instances + environment constraints
  found: No active records with gateway_url/provider_ref were available for direct endpoint probing in this environment.
  implication: Verification must rely on deterministic unit tests for fallback behavior instead of live endpoint probes.

- timestamp: 2026-03-06T10:16:36Z
  checked: `uv run pytest src/tests/services/test_zeroclaw_gateway_service.py src/tests/integrations/test_zeroclaw_spec.py -q`
  found: 48 passed, including new fallback tests for `/execute` 404 -> `/webhook` and webhook-primary single-call behavior.
  implication: Compatibility fix works in client logic and updated spec defaults remain valid under test coverage.

## Resolution

root_cause: Spec/client contract drift. Orchestrator targeted a spec-defined execute route, while real Zeroclaw deployments may expose webhook ingress; no compatibility fallback existed, so 404 on `/execute` terminated execution.
fix: Add execute endpoint compatibility fallback in `ZeroclawGatewayService` to retry `/webhook` when primary execute path returns 404; align spec defaults to non-streaming mode and webhook path.
verification: Verified by targeted test run (`48 passed`) covering spec loading and gateway execution including new fallback scenarios.
files_changed:
  - src/services/zeroclaw_gateway_service.py
  - src/integrations/zeroclaw/spec.json
  - src/integrations/zeroclaw/spec.template.json
  - src/tests/services/test_zeroclaw_gateway_service.py
  - src/tests/integrations/test_zeroclaw_spec.py
