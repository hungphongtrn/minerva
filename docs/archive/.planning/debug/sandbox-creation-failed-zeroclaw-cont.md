---
status: resolved
trigger: "Continue debugging sandbox-creation-failed-zeroclaw. Prior investigation identified legacy snapshot alias drift and applied remap, but issue persists."
created: 2026-03-08T08:29:25Z
updated: 2026-03-08T08:46:29Z
---

## Current Focus

hypothesis: Root cause and mitigation confirmed
test: validate focused tests and live provider provisioning path after timeout-cap adjustment
expecting: no synthetic 20s create timeout in failure path
next_action: report root cause, applied fix, and remaining upstream Daytona startup error

## Symptoms

expected: First /runs request provisions sandbox successfully and reaches active
actual: /runs provisioning fails after 3 attempts with create timeout even after snapshot remap
errors: "Provisioning failed after 3 attempts ... Failed to create sandbox: Function 'create' exceeded timeout of 20.0 seconds."
reproduction: Start server and submit first /runs request; failure observed in SSE and server log
started: Persists after applying snapshot alias remap from prior session

## Eliminated

- hypothesis: Legacy snapshot alias drift is the primary cause for current failure
  evidence: snapshot remap tests pass; preflight confirms zeroclaw-base exists; failure still occurs with env override to zeroclaw-base
  timestamp: 2026-03-08T08:29:25Z

## Evidence

- timestamp: 2026-03-08T08:29:25Z
  checked: .planning/debug/resolved/sandbox-creation-failed-zeroclaw.md
  found: prior fix remapped legacy snapshot aliases to zeroclaw-base and verified adapter-level behavior
  implication: current failure path likely has a different root cause beyond snapshot name remap

- timestamp: 2026-03-08T08:29:25Z
  checked: /tmp/minerva-oss-postfix.log and /tmp/oss-postfix-a1.sse
  found: preflight passes with snapshot zeroclaw-base, then sandbox hydration fails repeatedly with Daytona create timeout at 20s
  implication: failure occurs during Daytona create call in runtime path, not during preflight snapshot existence checks

- timestamp: 2026-03-08T08:30:15Z
  checked: src/infrastructure/sandbox/providers/daytona.py and src/config/settings.py
  found: provider hard-caps create timeout at 20s (PROVISION_CREATE_TIMEOUT_SECONDS) and there is no env setting to tune it
  implication: first-run creation can fail solely due to aggressive timeout policy even when snapshot exists and is correct

- timestamp: 2026-03-08T08:45:24Z
  checked: direct Daytona SDK create with settings target=eu and timeout=120
  found: create fails after ~33.75s with underlying Daytona error "Sandbox failed to start: sandbox exited with code 2"
  implication: observed /runs 20s timeout is a masking symptom; primary provider-side threshold is too short to expose true failure mode

- timestamp: 2026-03-08T08:46:29Z
  checked: src/tests/services/test_sandbox_provider_adapters.py targeted tests
  found: `uv run pytest ... -k "snapshot_name or daytona_provision_uses_explicit_image_config" -q` => 2 passed
  implication: timeout-cap adjustment does not regress provider adapter behavior covered by focused tests

- timestamp: 2026-03-08T08:46:29Z
  checked: live `provider.provision_sandbox` repro with zeroclaw-base after timeout-cap adjustment
  found: provisioning now fails with underlying Daytona create error ("Sandbox is in error state on runner") in ~6.9s, not 20s timeout
  implication: code fix removes misleading timeout failure path and exposes true upstream Daytona runner startup failure

## Resolution

root_cause: Provider hard-capped Daytona create timeout at 20s, which is shorter than real create latency/failure signaling and caused misleading "Function 'create' exceeded timeout of 20.0 seconds" errors that masked the actual runner startup failure.
fix: Increased Daytona provider create timeout cap from 20s to 60s so provisioning surfaces true Daytona create outcomes instead of synthetic local timeout.
verification: Focused adapter tests pass; live provider repro no longer returns the 20s timeout and now reports underlying Daytona runner error.
files_changed: [src/infrastructure/sandbox/providers/daytona.py]
