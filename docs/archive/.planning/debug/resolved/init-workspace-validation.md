---
status: resolved
trigger: "Fix the issue: init-workspace-validation - minerva init incorrectly requires workspace to exist in database, blocking OSS workflow"
created: 2026-03-03T10:00:00Z
updated: 2026-03-03T10:25:00Z
---

## Current Focus

hypothesis: Fix verified - init command now skips DB validation while serve still validates
test: Verified both paths work correctly
expecting: ✅ Both init and serve validation work as intended
next_action: Complete and archive debug session

## Symptoms

expected: `minerva init` should pass when MINERVA_WORKSPACE_ID env var is set (only validate env var, not DB existence)
actual: `minerva init` fails with WORKSPACE_CONFIGURED [BLOCKING] [FAIL] - Workspace '0824b1f9-39a6-4305-99db-b4b73db4cb80' not found in database
errors: "Workspace '0824b1f9-39a6-4305-99db-b4b73db4cb80' not found in database" → Run `minerva register` to create your workspace, then set MINERVA_WORKSPACE_ID.
reproduction: uv run minerva init
timeline: After phase 03.3 implementation - per planning phase 03.3-CONTEXT.md, OSS workflow should allow dev to set MINERVA_WORKSPACE_ID first, then register creates workspace if needed

## Evidence

- timestamp: 2026-03-03T10:00:00Z
  checked: src/cli/commands/init.py
  found: init.py calls `service.run_all_checks()` which runs all checks including workspace DB validation
  implication: init command has no way to skip DB validation

- timestamp: 2026-03-03T10:01:00Z
  checked: src/services/preflight_service.py _check_workspace_configured()
  found: Method validates env var set, "auto" mode, workspace exists in DB, AND workspace has packs
  implication: All validation happens in one method with no granularity

- timestamp: 2026-03-03T10:02:00Z
  checked: .planning/phases/03.3-close-pack-mount-isolation-and-identity-collision-gaps/03.3-CONTEXT.md lines 55-57
  found: "Validate MINERVA_WORKSPACE_ID at startup (preflight): check env var is set, workspace exists in DB... Server refuses to start if any check fails"
  implication: This refers to `minerva serve`, NOT `minerva init`

## Resolution

root_cause: PreflightService.run_all_checks() always performs full workspace validation including DB existence. The _check_workspace_configured() method validates: (1) env var is set, (2) not "auto", (3) workspace exists in DB, (4) workspace has packs. For `minerva init`, only steps 1-2 should be validated, allowing `minerva register` to create the workspace afterward.

fix: Split workspace check into two modes:
1. Added `include_workspace_db_validation` parameter to `run_all_checks()` (defaults to True for backward compatibility)
2. Added `include_db_validation` parameter to `_check_workspace_configured()` 
3. When `include_db_validation=False`, returns PASS after validating env var is set (skips DB existence and pack checks)
4. Updated `init.py` to call `run_all_checks(include_workspace_db_validation=False)`
5. `serve.py` unchanged - uses `check_workspace_configured()` public API which defaults to full validation

verification: 
- ✅ `minerva init` with non-existent workspace: PASS (only validates env var)
- ✅ `check_workspace_configured()` (serve path): FAIL (validates DB existence)
- OSS workflow now works: set MINERVA_WORKSPACE_ID → init passes → register creates workspace → serve validates

files_changed:
- src/services/preflight_service.py: Added include_workspace_db_validation parameter to run_all_checks() and include_db_validation to _check_workspace_configured()
- src/cli/commands/init.py: Call run_all_checks(include_workspace_db_validation=False)
