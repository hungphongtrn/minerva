---
status: investigating
trigger: "serve-startup-snapshot-and-bridge-failure: Standard startup `uv run minerva serve --port 8001` fails during snapshot preflight with `'tuple' object has no attribute 'name'`. With `--skip-preflight`, server starts but `/runs` fail with bridge transport error."
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:00:00Z
---

## Current Focus

hypothesis: Two distinct issues: (1) snapshot preflight code has a bug accessing tuple.name instead of tuple element, (2) bridge transport layer failing to execute assistant payloads
test: Read log files to identify exact error locations, then examine source code
expecting: Find the specific line causing 'tuple' object has no attribute 'name' and the bridge transport error root cause
next_action: Read both log files to gather initial evidence

## Symptoms

expected: `uv run minerva serve --port 8001` should start successfully after preflight; `/runs` should return real assistant output and complete successfully.
actual: Normal serve exits immediately during preflight with tuple.name error; skip-preflight serve starts but `/runs` fail via bridge transport error and no assistant output.
errors: `Failed to check snapshot: 'tuple' object has no attribute 'name'`; SSE failed events with bridge failure and recovery reprovisioning failed.
reproduction: Bring infra up with docker compose, run `uv sync`, `uv run alembic upgrade head`, `uv run minerva init`, then `uv run minerva serve --port 8001` (fails). Retry with `--skip-preflight`, call `/health` (healthy) and `/runs` (fails).
started: Current state after recent phase work; verified today against current environment.

## Eliminated

## Evidence

- timestamp: 2026-03-03T00:00:00Z
  checked: /tmp/minerva-serve-8001.log
  found: "Error: 'tuple' object has no attribute 'name' during snapshot preflight check"
  implication: Code iterating over snapshots directly instead of snapshots.items

- timestamp: 2026-03-03T00:00:00Z
  checked: src/services/preflight_service.py line 208-209
  found: "Code does 'return any(s.name == snapshot_name for s in snapshots)' but snapshots is PaginatedSnapshots, not list"
  implication: Daytona SDK returns PaginatedSnapshots with .items attribute containing actual snapshots

- timestamp: 2026-03-03T00:00:00Z
  checked: /tmp/minerva-serve-8001-skip.log
  found: "Bridge execution failed after 1 attempts. Recovery reprovisioning failed. (bridge_transport_error)"
  implication: Bridge trying to connect to simulated local compose sandbox URL that doesn't exist

- timestamp: 2026-03-03T00:00:00Z
  checked: src/infrastructure/sandbox/providers/local_compose.py
  found: "Local compose provider is a simulation - no actual containers are created, just in-memory state"
  implication: Bridge cannot connect to http://local-sandbox-ac617e6baca8:18790 because it's not a real endpoint

## Resolution

root_cause: 
  - Issue 1: preflight_service.py iterates over PaginatedSnapshots object instead of its .items attribute. The Daytona SDK's snapshot.list() returns a PaginatedSnapshots wrapper object, not a list. Code was accessing s.name on the wrapper instead of the actual snapshot items.
  - Issue 2: local_compose provider is a simulation that doesn't run a real Picoclaw gateway. Bridge was trying to connect to simulated URLs like 'http://local-sandbox-{hash}:18790' that don't exist, causing transport errors.
fix: 
  - Fix 1: Changed 'for s in snapshots' to 'for s in snapshots.items' in preflight_service.py line 209
  - Fix 2: Added _is_local_compose_url() helper to detect local compose sandboxes and fail fast with a clear error message instead of attempting bridge connection that will fail with transport error
verification: 
  - Server starts successfully with all preflight checks passing
  - Picoclaw snapshot check now correctly detects snapshot existence
  - Bridge execution with local compose now returns clear error: "Bridge execution not available: local compose sandbox has no Picoclaw gateway. Use Daytona infrastructure for full execution."
files_changed: 
  - src/services/preflight_service.py
  - src/services/run_service.py
