---
status: resolved
trigger: "Investigate issue: zeroclaw-snapshot-and-daytona-provisioning"
created: 2026-03-06T11:37:35Z
updated: 2026-03-06T11:43:09Z
---

## Current Focus

hypothesis: Confirmed and fixed: monorepo Dockerfile selection, writable workspace path, and failed-provision cleanup.
test: Targeted pytest runs covering snapshot Dockerfile selection, identity path checks under /workspace, and post-create stop cleanup on provisioning failure.
expecting: All targeted regression tests pass.
next_action: Session complete; report root cause and applied fixes.

## Symptoms

expected: minerva snapshot build can build a new snapshot from Zeroclaw repo, /runs provisions sandbox and returns agent output, and failed provisions do not leave running sandboxes.
actual: snapshot build fails with missing rust-toolchain.toml path in temp clone; /runs SSE ends with failed event (mkdir -p /home/daytona/workspace permission denied); failed attempts leave Daytona sandboxes STARTED until manually stopped/deleted.
errors: Failed to create snapshot: Path does not exist: .../picoclaw/rust-toolchain.toml; Provisioning failed after 3 attempts ... mkdir -p /home/daytona/workspace; Permission denied; observed leaked sandboxes via Daytona list after failed /runs.
reproduction: 1) uv run minerva snapshot build --repo-url "https://github.com/openagen/zeroclaw" --ref "main" --name "zeroclaw-base" 2) start DB + migrate 3) uv run minerva serve --skip-preflight --host 127.0.0.1 --port 8002 4) POST /runs with X-User-ID + X-Session-ID and JSON message 5) inspect Daytona sandboxes; failures can remain STARTED.
started: observed in current session while validating end-to-end messaging and snapshot replacement.

## Eliminated

## Evidence

- timestamp: 2026-03-06T11:37:53Z
  checked: Codebase symbol search for snapshot build and Daytona workspace provisioning
  found: Snapshot workflow is implemented in src/services/daytona_snapshot_build_service.py and provisioning path in src/infrastructure/sandbox/providers/daytona.py
  implication: Root causes are likely concentrated in these two modules and their tests can be updated targetedly

- timestamp: 2026-03-06T11:39:11Z
  checked: Full read of daytona_snapshot_build_service.py, daytona provider, orchestrator retry paths, and zeroclaw spec
  found: _build_image currently prefers root Dockerfile and may copy docker/Dockerfile to root; WORKSPACE_PATH is /home/daytona/workspace and used in mkdir/symlink/identity checks; provision_sandbox raises on post-create failures without stopping created sandbox
  implication: Exact failure signatures match reported symptoms (missing rust-toolchain path, mkdir permission denied, leaked STARTED sandboxes on failed retries)

- timestamp: 2026-03-06T11:42:22Z
  checked: Implemented minimal code changes and regression tests
  found: Snapshot builder now prefers picoclaw/Dockerfile and no longer copies Dockerfiles; workspace path constant changed to /workspace; Daytona provider now best-effort stops partially created sandboxes on post-create failure
  implication: Changes directly target all three reported failure mechanisms while preserving existing service interfaces

- timestamp: 2026-03-06T11:43:09Z
  checked: Targeted verification test commands
  found: 3/3 snapshot build tests passed, identity verification path test passed, and cleanup-on-failure Daytona provisioning test passed
  implication: Fixes are validated for the reported breakpoints and protected by regression tests

## Resolution

root_cause: Snapshot build selected an unsuitable Dockerfile path for Zeroclaw monorepo layouts; Daytona provisioning used an unwritable workspace path (/home/daytona/workspace) in this runtime; and provider failures after sandbox creation did not perform cleanup, leaving STARTED sandboxes.
fix: Implemented targeted fixes in snapshot build dockerfile selection, workspace path, and failed Daytona provisioning cleanup.
verification: uv run pytest src/tests/services/test_phase3_2_snapshot_build.py -k "build_image"; uv run pytest src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py -k "verify_identity_files_checks_required_files"; uv run pytest src/tests/services/test_sandbox_provider_adapters.py -k "provision_stops_partial_sandbox_on_post_create_failure" (all passed).
files_changed: ["src/services/daytona_snapshot_build_service.py", "src/infrastructure/sandbox/providers/base.py", "src/infrastructure/sandbox/providers/daytona.py", "src/tests/services/test_phase3_2_snapshot_build.py", "src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py", "src/tests/services/test_sandbox_provider_adapters.py"]
