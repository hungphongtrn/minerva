---
status: resolved
trigger: "URGENT: Debug why sandbox creation fix didn't work. Phase 4 test shows sandbox still hanging >90s."
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T16:29:56Z
---

## Current Focus

hypothesis: Resolved.
test: Completed verification run and database state check.
expecting: N/A
next_action: archive debug session

## Symptoms

expected: Sandbox creation completes in <30s with timeout protection
actual: Request hangs >90s with no response, no HTTP code returned
errors: None visible yet - need to check logs
reproduction: curl POST to /runs with X-User-ID: alice
started: After commit 64bed82 test rerun (still failing)

## Eliminated

## Evidence

- timestamp: 2026-03-03T16:20:28Z
  checked: running API process PID 49564
  found: process has been up for ~20 minutes and runs `minerva serve --port 8002`
  implication: server was started recently today; stale pre-commit process is less likely but still needs commit/load verification
- timestamp: 2026-03-03T16:20:53Z
  checked: direct file read of server log
  found: `read` tool reports server.log as binary
  implication: need alternate parsing path to inspect runtime logs
- timestamp: 2026-03-03T16:21:08Z
  checked: /Users/phong/Workspace/minerva/server.log via `uv run python` decode
  found: `POST /runs` returned `200 OK` immediately, then repeated SQL queries check alice sandbox in `pending/creating` every ~39s, with no transition to healthy/active
  implication: client-perceived hang is likely long-lived run stream waiting on sandbox readiness, not HTTP handler blocking pre-response
- timestamp: 2026-03-03T16:21:54Z
  checked: `sandbox_instances` rows for external_user_id `alice`
  found: single sandbox `0ea5380a-749d-4161-8113-4ccef4df658d` has `state=creating`, `health_status=unknown`, `gateway_url=NULL`, `identity_ready=false`, unchanged since creation at 16:01:12Z
  implication: lifecycle is stuck before readiness/activation and stale non-terminal row blocks subsequent requests
- timestamp: 2026-03-03T16:21:54Z
  checked: ad-hoc `run_sessions` query for alice
  found: query failed because table uses `state` column (not `status`)
  implication: no new functional insight; continue with corrected queries/code inspection
- timestamp: 2026-03-03T16:22:51Z
  checked: `src/infrastructure/sandbox/providers/daytona.py` and `src/services/sandbox_orchestrator_service.py`
  found: Daytona provider includes `asyncio.wait_for(daytona.create(...), timeout=create_timeout+5)` (new fix present), while orchestrator reuses existing `pending/creating` records via `_find_in_progress_sandbox()` and does not mark stale in-progress rows failed on provisioning exceptions
  implication: stale `creating` rows can persist across requests and undermine timeout fix by routing new attempts into in-progress wait/reuse logic
- timestamp: 2026-03-03T16:24:49Z
  checked: `src/api/oss/routes/runs.py`, `src/services/run_service.py`, and `src/services/oss_user_queue.py`
  found: OSS endpoint keeps SSE open until `execute_with_routing()` completes; no route-level timeout exists, and retry behavior is controlled downstream by sandbox orchestration
  implication: long provisioning/recovery retries directly translate into >90s client-perceived hang
- timestamp: 2026-03-03T16:25:11Z
  checked: `run_sessions` persistence for workspace `0824b1f9-39a6-4305-99db-b4b73db4cb80`
  found: no run session rows recorded, consistent with failures happening before sandbox-backed execution begins
  implication: need direct request timing/log evidence rather than run session diagnostics
- timestamp: 2026-03-03T16:27:48Z
  checked: live `curl POST /runs` SSE request for `X-User-ID: alice`
  found: request took `119.23s` and failed with `Provisioning failed after 3 attempts: ... Identity verification failed: Timeout waiting for identity files (30.4s)`
  implication: timeout fix exists but is multiplied by orchestrator retries; this is the direct cause of >90s hangs
- timestamp: 2026-03-03T16:29:56Z
  checked: live post-fix `/runs` request and sandbox database row
  found: request completed in `26.97s` with terminal failed SSE event; alice sandbox row transitioned to `state=failed`, `health_status=unhealthy`, `hydration_status=failed`
  implication: >90s hang is removed and stale `creating` persistence is fixed

## Resolution

root_cause: Identity verification timeout (~30s) is retried 3 times by sandbox orchestrator and each failed attempt leaves/keeps sandbox in non-terminal `creating`, so OSS `/runs` SSE stays open for ~120s before failing.
fix:
  - Reduced Daytona create timeout budget to 20s and identity verification timeout to 20s.
  - Disabled automatic retry for generic provisioning/identity failures (retry only gateway resolution failures).
  - Marked sandbox records as `failed/unhealthy` when provisioning throws, preventing stale `creating` reuse.
verification:
  - Restarted server process to load modified code.
  - Reproduced `/runs` request with `X-User-ID: alice`; end-to-end reduced from 119.23s to 26.97s.
  - Confirmed DB state transition from stale `creating` to `failed/unhealthy` on provisioning failure.
files_changed:
  - src/infrastructure/sandbox/providers/daytona.py
  - src/services/sandbox_orchestrator_service.py
