---
status: resolved
trigger: "Investigate new blocker after runner/snapshot fix path: sandbox provisioning now fails with workspace symlink permission error."
created: 2026-03-08T09:22:11Z
updated: 2026-03-08T09:30:28Z
---

## Current Focus

hypothesis: Permission blocker is resolved by writable-path fallback from `/workspace` to `$HOME/workspace` when mount parent ownership cannot be repaired.
test: Validate with focused tests and live `/runs` repro using rebuilt snapshot.
expecting: `/runs` no longer fails on `ln -sf /workspace/... Permission denied`; provisioning advances further.
next_action: resolved

## Symptoms

expected: /runs provisions sandbox and starts bridge
actual: fails during _create_workspace_symlinks
errors: "Sandbox command failed (exit=1): ln -sf /workspace/pack/AGENT.md /workspace/AGENT.md; stderr=ln: /workspace/AGENT.md: Permission denied"
reproduction: Start server with DAYTONA_PICOCLAW_SNAPSHOT_NAME=zeroclaw-base-rebuild-fix-1772961211 and POST /runs
started: appears after replacing bad zeroclaw-base snapshot with rebuilt snapshot

## Eliminated

## Evidence

- timestamp: 2026-03-08T09:22:11Z
  checked: reporter-provided symptom/evidence bundle
  found: snapshot user is uid=1000(picoclaw), HOME=/home/picoclaw, no /workspace by default, permission denied while linking under /workspace
  implication: provisioning code likely relies on environment-level writable /workspace invariant that rebuilt snapshot no longer guarantees

- timestamp: 2026-03-08T09:24:46Z
  checked: /tmp/minerva-oss-runnerfix.log
  found: every failed hydrate attempt ends at `ln -sf /workspace/pack/AGENT.md /workspace/AGENT.md` permission denied; error is deterministic across retries
  implication: failure is local filesystem permission at symlink target creation, not transient runner/network issue

- timestamp: 2026-03-08T09:24:46Z
  checked: src/infrastructure/sandbox/providers/daytona.py:_create_workspace_symlinks
  found: function does `mkdir -p /workspace` then immediate `ln -sf` operations with no writability check/ownership repair
  implication: code assumes writable `/workspace`; rebuilt snapshot violates this assumption when mount parent is root-owned

- timestamp: 2026-03-08T09:26:32Z
  checked: uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py
  found: new tests passed; 2 pre-existing failures in same module reference legacy Picoclaw config shape/paths (`/home/daytona/.picoclaw`, `channels.bridge`)
  implication: full module is not a clean regression signal for this change; targeted test selection is required for this bug verification

- timestamp: 2026-03-08T09:30:28Z
  checked: uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py -k TestWorkspaceSymlinkPermissions
  found: 3 selected tests passed (permission preflight, fallback-to-home workspace, explicit error path)
  implication: code path for workspace permission handling behaves as designed

- timestamp: 2026-03-08T09:30:28Z
  checked: live repro on local server (snapshot `zeroclaw-base-rebuild-fix-1772961211`) with POST /runs
  found: failure moved from `ln -sf /workspace/pack/AGENT.md /workspace/AGENT.md: Permission denied` to later stage `Failed to write Zeroclaw config: Failed to create folder`
  implication: workspace symlink permission blocker is fixed; next independent provisioning blocker is config directory creation permissions

## Resolution

root_cause:
root_cause: Daytona provisioning assumes `/workspace` is writable by sandbox user; when snapshot mount creates root-owned `/workspace`, symlink creation fails because provider does not preflight/repair permissions.
fix: Added workspace writable-preflight in Daytona symlink setup that attempts ownership/mode repair (`chown` then `sudo chown`, `chmod` then `sudo chmod`) and fails early with explicit error if `/workspace` is still not writable; added focused unit tests for preflight + failure path.
verification:
  - `uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py -k TestWorkspaceSymlinkPermissions` -> 3 passed
  - Live `/runs` repro no longer emits workspace symlink permission error; now fails later at config write stage
files_changed:
  - src/infrastructure/sandbox/providers/daytona.py
  - src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py
