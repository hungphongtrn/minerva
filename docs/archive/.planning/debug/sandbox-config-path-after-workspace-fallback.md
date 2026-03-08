---
status: resolved
trigger: "Continue debugging next blocker after workspace permission fix: provisioning now fails writing Zeroclaw config folder."
created: 2026-03-08T09:35:04Z
updated: 2026-03-08T09:43:13Z
---

## Current Focus

hypothesis: Fix is verified if live `/runs` no longer fails at config folder creation and shows runtime launched with fallback-config path.
test: Reproduced via fresh local server (`DAYTONA_PICOCLAW_SNAPSHOT_NAME=zeroclaw-base-rebuild-fix-1772961211`) and POST `/runs` SSE capture.
expecting: Config-write error disappears; any remaining failure should occur later in lifecycle.
next_action: resolved

## Symptoms

expected: provisioning writes runtime config and starts bridge
actual: fails at config write stage
errors: "Failed to write Zeroclaw config: Failed to create folder"
reproduction: DAYTONA_PICOCLAW_SNAPSHOT_NAME=zeroclaw-base-rebuild-fix-1772961211 + POST /runs
started: after workspace permission fix when rebuilt snapshot has non-writable /workspace

## Eliminated

## Evidence

- timestamp: 2026-03-08T09:35:04Z
  checked: user report and provided evidence
  found: workspace fallback exists, but `spec.runtime.config_path` remains `/workspace/.zeroclaw/config.json`
  implication: config write/start path may still target non-writable location despite fallback

- timestamp: 2026-03-08T09:35:46Z
  checked: `src/infrastructure/sandbox/providers/daytona.py` provisioning and runtime start flow
  found: `provision_sandbox()` writes config to `config_path = spec.runtime.config_path`; `_start_bridge_runtime()` executes `start_cmd = spec.runtime.start_command` with no workspace fallback substitution
  implication: when `/workspace` is not writable and fallback workspace is used, both mkdir/upload and runtime start still point to `/workspace/.zeroclaw/config.json`

- timestamp: 2026-03-08T09:36:26Z
  checked: `src/infrastructure/sandbox/providers/daytona.py` patch
  found: added `_resolve_runtime_config_path()`, provision now resolves config path from effective `workspace_path`, and `_start_bridge_runtime()` accepts `config_path` override to substitute start command path
  implication: config write and bridge start both align with fallback workspace path

- timestamp: 2026-03-08T09:37:54Z
  checked: `src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py`
  found: added focused tests for runtime config path rewrite, start command substitution, and fallback-aware provisioning path propagation
  implication: regression coverage now directly validates the failure mode and requested behavior

- timestamp: 2026-03-08T09:38:17Z
  checked: focused pytest run (`-k WorkspaceFallbackRuntimeConfigPath`)
  found: 1/3 tests failed due to test harness bug (`provider._exec_checked` restored after patch context)
  implication: product code behavior still unproven by this test until mock assertion is corrected

- timestamp: 2026-03-08T09:38:52Z
  checked: focused pytest rerun after harness fix
  found: assertion failed because fallback command string includes `/workspace/.zeroclaw/config.json` as substring within `/home/picoclaw/workspace/...`
  implication: assertion must validate config flag token, not broad substring containment

- timestamp: 2026-03-08T09:39:42Z
  checked: focused pytest (`src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py -k WorkspaceFallbackRuntimeConfigPath`)
  found: 3 tests passed covering config path rewrite, start command substitution, and fallback propagation during provisioning
  implication: code fix works in targeted unit scenarios; proceed to live repro for end-to-end confirmation

- timestamp: 2026-03-08T09:43:13Z
  checked: live repro on local server port 8003 with snapshot `zeroclaw-base-rebuild-fix-1772961211` and `POST /runs`
  found: failure changed from config-folder write error to runtime start error (`zeroclaw-gateway --config /tmp/workspace/.zeroclaw/config.json; sh: zeroclaw-gateway: not found`)
  implication: config path fallback is now applied in both write/start flows; original blocker is fixed and next blocker is missing runtime binary in snapshot

## Resolution

root_cause: Daytona provider used static `spec.runtime.config_path` and `spec.runtime.start_command` bound to `/workspace` even after selecting fallback writable workspace, causing config folder creation failure and potential bridge start misconfiguration.
fix: Resolved runtime config path from effective workspace path and threaded that path into both config file materialization and bridge start command substitution.
verification: "Focused tests pass (3/3). Live repro confirms original error removed; provisioning now fails later at bridge startup due to missing `zeroclaw-gateway` binary, with start command using fallback config path `/tmp/workspace/.zeroclaw/config.json`."
files_changed:
  - src/infrastructure/sandbox/providers/daytona.py
