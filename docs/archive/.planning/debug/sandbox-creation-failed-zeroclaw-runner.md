---
status: resolved
trigger: "Continue debugging sandbox-creation-failed-zeroclaw. User chose: debug runner/snapshot health directly."
created: 2026-03-08T08:58:19Z
updated: 2026-03-08T09:42:11Z
---

## Current Focus

hypothesis: root cause confirmed and remediation validated
test: verify patched snapshot build path + fresh snapshot startup
expecting: rebuild succeeds and new snapshot starts cleanly in eu
next_action: report root cause, evidence, and mitigation/fix plan to user

## Symptoms

expected: Sandbox created from zeroclaw-base reaches active and run proceeds
actual: Provisioning retries fail; sandbox creation ends with runner error state and exit code 2
errors: "Failed to create sandbox: Sandbox failed to start: sandbox exited with code 2" and "Sandbox is in error state on runner"
reproduction: start OSS server, submit POST /runs, observe SSE failed event and server hydration error
started: after zeroclaw migration; persists after snapshot alias remap and timeout adjustment

## Eliminated

- hypothesis: timeout cap (20s) is the primary root cause of current failure
  evidence: timeout increase surfaces same underlying runner startup failure now returned directly by Daytona create
  timestamp: 2026-03-08T08:58:19Z

## Evidence

- timestamp: 2026-03-08T08:58:19Z
  checked: .planning/debug/resolved/sandbox-creation-failed-zeroclaw.md
  found: earlier session fixed snapshot alias drift and validated adapter mapping to zeroclaw-base
  implication: current failure is not caused by legacy snapshot name resolution in provider factory

- timestamp: 2026-03-08T08:58:19Z
  checked: .planning/debug/sandbox-creation-failed-zeroclaw-cont.md
  found: direct provider repro already captured Daytona error "sandbox exited with code 2" / "Sandbox is in error state on runner"
  implication: underlying issue originates in Daytona runner/create lifecycle, not Minerva orchestration logic

- timestamp: 2026-03-08T08:58:19Z
  checked: /tmp/minerva-oss-postfix.log and /tmp/oss-postfix-a2.sse
  found: preflight snapshot check passes for zeroclaw-base, but /runs fails during hydration with Daytona create runner error
  implication: snapshot existence is necessary but insufficient; runner startup of created sandbox is failing

- timestamp: 2026-03-08T09:01:47Z
  checked: direct SDK snapshot list probe via `uv run python`
  found: Daytona responds successfully in target us using api_url=https://app.daytona.io/api, but SDK returns PaginatedSnapshots object (not list)
  implication: need adjusted probing script; connectivity/auth to Daytona is healthy and investigation can continue at snapshot/runner level

- timestamp: 2026-03-08T09:03:43Z
  checked: adjusted SDK snapshot introspection
  found: zeroclaw-base snapshot is active with id 822214ed-3010-4e9e-81d6-83c1509fc348, initial_runner_id=e4b93abf-cd29-4971-a9b4-440d6dc309fa, ref=cr.app.daytona.io/...:daytona, image_name is empty
  implication: Daytona has a resolvable active snapshot object; need to determine whether startup failure is tied to runner/target placement

- timestamp: 2026-03-08T09:07:21Z
  checked: direct create probes across targets using same snapshot
  found: eu target fails after ~32s with "timeout waiting for the sandbox to start - please ensure that your entrypoint is long-running"; us target fails quickly with "Snapshot zeroclaw-base is not available in region us"
  implication: zeroclaw-base is eu-scoped and the operative failure is startup on eu runner, consistent with non-long-running entrypoint or broken startup process in snapshot

- timestamp: 2026-03-08T09:11:04Z
  checked: eu create probe from plain image `debian:trixie-slim`
  found: sandbox creation succeeds in ~2.09s and reaches SandboxState.STARTED (cleanup completed afterward)
  implication: Daytona eu control plane and runner capacity are healthy; failure is specific to zeroclaw-base snapshot startup path

- timestamp: 2026-03-08T09:16:02Z
  checked: labeled eu snapshot create + SDK list/get inspection
  found: create throws `Failed to create sandbox: Sandbox failed to start: sandbox exited with code 2`; matched sandbox has `state=error`, `error_reason='sandbox exited with code 2, reason:'`, `snapshot='zeroclaw-base'`, runner_id=2bd30165-78ca-47b0-87b7-4bd961313726
  implication: exact failing condition is runner-level process exit code 2 during startup of snapshot-based sandbox

- timestamp: 2026-03-08T09:16:02Z
  checked: repeated snapshot create attempts and successful image create runner IDs
  found: both snapshot failures and image success land on the same runner id 2bd30165-78ca-47b0-87b7-4bd961313726
  implication: runner itself is operational; failure is tied to zeroclaw-base snapshot startup, not node-level outage

- timestamp: 2026-03-08T09:20:52Z
  checked: create from snapshot backing registry ref
  found: direct image pull from snapshot ref fails with unauthorized pull error for private `cr.app.daytona.io/sbox/...` repository
  implication: cannot directly compare snapshot image contents via public image create; need alternative validation path

- timestamp: 2026-03-08T09:22:26Z
  checked: direct create from configured base image `daytonaio/workspace-picoclaw:latest`
  found: create fails with BUILD_FAILED because image pull is denied/repository unavailable
  implication: local env base image is stale/broken for direct image provisioning and cannot serve as reliable fallback path

- timestamp: 2026-03-08T09:24:53Z
  checked: CreateSandboxFromSnapshotParams schema and attempted command override
  found: snapshot params do not support command/entrypoint override fields; create still fails in ~31s with runner error state
  implication: startup command cannot be altered at create-time; next isolatable lever is os_user

- timestamp: 2026-03-08T09:28:24Z
  checked: snapshot create with `os_user='picoclaw'`
  found: failure unchanged (`sandbox exited with code 2`) and tagged error-state sandbox records user=picoclaw
  implication: user mismatch is not the root cause; startup binary/process in snapshot fails regardless of selected os_user

- timestamp: 2026-03-08T09:28:24Z
  checked: snapshot inventory in target eu
  found: only custom runtime snapshot is `zeroclaw-base`; all other active snapshots are generic daytonaio/debian variants
  implication: immediate mitigation can switch to generic snapshot/image only with reduced zeroclaw pre-bake guarantees

- timestamp: 2026-03-08T09:31:49Z
  checked: exec diagnostics on ERROR-state sandbox
  found: `process.exec` fails with `no IP address found. Is the Sandbox started?`
  implication: runner startup crash occurs before sandbox networking/process API is available; root-cause diagnostics must come from snapshot build/provenance, not in-sandbox logs

- timestamp: 2026-03-08T09:35:43Z
  checked: fresh snapshot rebuild attempt (`zeroclaw-base-rebuild-*`) via DaytonaSnapshotBuildService
  found: build fails before snapshot creation with `Path does not exist ... /picoclaw/docker/go.mod`
  implication: builder used docker/ as context for docker/Dockerfile, breaking `COPY go.mod` expectations; snapshot regeneration path is currently broken

- timestamp: 2026-03-08T09:42:11Z
  checked: patched snapshot build service + live rebuild
  found: `zeroclaw-base-rebuild-fix-1772961211` snapshot builds successfully to ACTIVE (no missing-path failure)
  implication: build-context bug is fixed, enabling rapid regeneration/rotation of broken snapshots

- timestamp: 2026-03-08T09:42:11Z
  checked: direct create probe from rebuilt snapshot in eu
  found: sandbox starts in ~2.98s with state STARTED and no error_reason, then deletes cleanly
  implication: runner/create path is healthy; original failure is isolated to stale/broken `zeroclaw-base` snapshot artifact

- timestamp: 2026-03-08T09:42:11Z
  checked: unit tests `uv run pytest src/tests/services/test_phase3_2_snapshot_build.py -k "build_image" -q`
  found: 6 passed (including new docker-subdir context regression test)
  implication: code fix is covered and no regressions in build-image path tests

## Resolution

root_cause: The active Daytona snapshot `zeroclaw-base` in eu is a bad artifact that consistently exits during runner startup (`error_reason: sandbox exited with code 2`). This was compounded by a bug in snapshot rebuild tooling: for repos using `docker/Dockerfile`, the builder used `docker/` as context, causing `COPY go.mod` failures and preventing regeneration of a healthy replacement snapshot.
fix: Updated `DaytonaSnapshotBuildService._build_image` to relocate `docker/Dockerfile` into repo-root context (`.daytona-builder.Dockerfile`) when root-level `go.mod` exists, then build from that effective Dockerfile. Added a regression test covering this layout.
verification: Confirmed old `zeroclaw-base` still fails with code 2 on eu runner; built fresh snapshot `zeroclaw-base-rebuild-fix-1772961211` successfully after patch; direct create from fresh snapshot reaches STARTED in ~3s; targeted build-image tests pass.
files_changed: [src/services/daytona_snapshot_build_service.py, src/tests/services/test_phase3_2_snapshot_build.py]
