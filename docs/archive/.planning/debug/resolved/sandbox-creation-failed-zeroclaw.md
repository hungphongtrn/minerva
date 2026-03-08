---
status: resolved
trigger: "Investigate issue: sandbox-creation-failed-zeroclaw"
created: 2026-03-08T08:19:44Z
updated: 2026-03-08T08:25:32Z
---

## Current Focus

hypothesis: Root cause confirmed and minimal fix verified
test: Validate runtime snapshot resolution plus focused provider tests
expecting: provider uses zeroclaw-base with legacy env and tests pass
next_action: Archive session and report root cause + fix details

## Symptoms

expected: Sandbox reaches active
actual: Sandbox state error during provisioning; run fails
errors: user reported unknown primary; observed by orchestrator: (a) "Provisioning failed after 3 attempts ... Function 'create' exceeded timeout of 20.0/60.0 seconds" and (b) "Sandbox failed to start: sandbox exited with code 2"
reproduction: CLI serve then curl
started: After zeroclaw, it has never worked

## Eliminated

- hypothesis: Zeroclaw runtime start command is the primary failing step
  evidence: provider executes daytona.create before _start_bridge_runtime; observed errors are thrown from create
  timestamp: 2026-03-08T08:22:53Z

## Evidence

- timestamp: 2026-03-08T08:21:18Z
  checked: /tmp/minerva-oss-e2e-run.log
  found: /runs creates sandbox rows successfully, then hydration fails with "Failed to create sandbox: Sandbox failed to start: sandbox exited with code 2" and in another attempt "Function 'create' exceeded timeout of 60.0 seconds"
  implication: Failure is in Daytona provisioning/startup phase, not DB lease/run queue pipeline

- timestamp: 2026-03-08T08:21:18Z
  checked: /tmp/oss-e2e-a1.sse and /tmp/oss-e2e-a2.sse
  found: both runs fail during provisioning with identical create failure before any successful bridge execution
  implication: Problem is reproducible and systemic for sandbox bootstrap

- timestamp: 2026-03-08T08:21:18Z
  checked: repository search for snapshot identifiers
  found: tests still reference legacy names like picoclaw-base/picoclaw-snapshot; runtime snapshot default appears in provider code
  implication: zeroclaw migration may not be fully propagated through runtime configuration

- timestamp: 2026-03-08T08:22:53Z
  checked: src/infrastructure/sandbox/providers/daytona.py
  found: DaytonaError from daytona.create is raised before workspace symlink/config/runtime bootstrap; _start_bridge_runtime runs only after create succeeds
  implication: exit code 2/timeout originates in base image/snapshot startup during create, not in zeroclaw gateway start command

- timestamp: 2026-03-08T08:22:53Z
  checked: src/config/settings.py and .env
  found: settings and local env still carry Picoclaw defaults/value (DAYTONA_BASE_IMAGE=daytonaio/workspace-picoclaw:latest, DAYTONA_PICOCLAW_SNAPSHOT_NAME=picoclaw-base)
  implication: provisioning likely targets legacy runtime artifacts despite zeroclaw migration

- timestamp: 2026-03-08T08:23:52Z
  checked: uv run provider introspection
  found: effective provider config currently resolves snapshot=picoclaw-base, base_image=daytonaio/workspace-picoclaw:latest, target=eu
  implication: runtime is definitely using legacy snapshot at provisioning time

- timestamp: 2026-03-08T08:24:27Z
  checked: src/infrastructure/sandbox/providers/factory.py change + uv introspection
  found: with .env still set to picoclaw-base, provider now resolves snapshot as zeroclaw-base
  implication: migration drift on snapshot naming is corrected at provider construction

- timestamp: 2026-03-08T08:24:57Z
  checked: uv run pytest src/tests/services/test_sandbox_provider_adapters.py -k snapshot_name
  found: test failed because it expected provider._snapshot_name == picoclaw-base; runtime now resolves zeroclaw-base by design
  implication: tests must be aligned with compatibility remap behavior

## Resolution

root_cause: Legacy Daytona snapshot name (picoclaw-base) remained in runtime configuration after zeroclaw migration, so /runs provisioned with outdated snapshot artifacts and failed during daytona.create with startup exit code 2 / create timeout.
fix: Added compatibility remap in Daytona provider factory to translate legacy snapshot aliases (picoclaw-base, picoclaw-snapshot) to zeroclaw-base; align tests accordingly.
verification: `uv run python -c ...get_provider('daytona')...` shows env `picoclaw-base` resolves to provider `zeroclaw-base`; `uv run pytest src/tests/services/test_sandbox_provider_adapters.py -k snapshot_name` passes.
files_changed: [src/infrastructure/sandbox/providers/factory.py, src/tests/services/test_sandbox_provider_adapters.py]
