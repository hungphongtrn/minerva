---
status: investigating
trigger: "Fix sandbox provisioning failures: permission denied creating /home/daytona/workspace and lease contention on retry"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:00:00Z
---

## Current Focus

hypothesis: Permission failure comes from using /home/daytona/workspace in a runtime where only /workspace is writable; lease contention is caused by missing release in one failure path.
test: Inspect Daytona provider workspace path/creation behavior and orchestrator lease acquire/release paths including exceptions and retries.
expecting: Find hardcoded /home/daytona/workspace command and at least one execution path where lease release is skipped after provisioning failure.
next_action: Read provider and orchestrator files completely and capture evidence.

## Symptoms

expected: Sandbox provisioning succeeds and retry works without lease contention.
actual: mkdir -p /home/daytona/workspace fails with Permission denied; retry then fails with active lease contention timeout; sandbox ends failed.
errors: mkdir -p /home/daytona/workspace -> Permission denied; active lease held ... contention timeout.
reproduction: Create sandbox in Daytona, provisioning attempts workspace creation, fails, retry provisioning shortly after.
started: Observed at Phase 4a in current test flow.

## Eliminated

## Evidence

## Resolution

root_cause: 
fix: 
verification: 
files_changed: []
