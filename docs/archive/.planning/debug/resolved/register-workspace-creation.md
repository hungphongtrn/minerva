---
status: resolved
trigger: "Fix register issues above. `minerva register` should create workspace when MINERVA_WORKSPACE_ID is set but workspace doesn't exist in DB."
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:00:00Z
---

## Current Focus

hypothesis: The _resolve_workspace_id() function at lines 80-92 raises ValueError when workspace doesn't exist, instead of creating it
test: Modify the code to create workspace with the specified UUID instead of raising error
expecting: Workspace should be created with MINERVA_WORKSPACE_ID if it doesn't exist
next_action: Fix the code at lines 85-89 to create workspace instead of raising ValueError

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: If MINERVA_WORKSPACE_ID is set in .env but workspace doesn't exist in DB, `minerva register` should CREATE the workspace with that ID and register the pack to it
actual: `minerva register` raises ValueError "Workspace not found: {workspace_id}" when MINERVA_WORKSPACE_ID is set but workspace doesn't exist
errors: ValueError: Workspace not found: 0824b1f9-39a6-4305-99db-b4b73db4cb80
reproduction: 1. Set MINERVA_WORKSPACE_ID=some-uuid in .env (workspace doesn't exist), 2. Run `minerva register <pack-path>`
started: After phase 03.3 implementation - OSS workflow requires dev to set MINERVA_WORKSPACE_ID first, then register creates workspace

## Eliminated

## Evidence

- timestamp: 2026-03-03
  checked: src/cli/commands/register.py lines 80-92
  found: Lines 85-89 check if workspace exists and raise ValueError if not found
  implication: When MINERVA_WORKSPACE_ID is set but workspace doesn't exist, it fails instead of creating

- timestamp: 2026-03-03
  checked: src/cli/commands/register.py lines 113-145
  found: Code already exists to create a default workspace with auto-generated UUID when no workspaces exist
  implication: We can reuse the workspace creation logic but with the explicit UUID from MINERVA_WORKSPACE_ID

- timestamp: 2026-03-03
  checked: .planning/phases/03.3-close-pack-mount-isolation-and-identity-collision-gaps/03.3-CONTEXT.md lines 23-25
  found: Design intent is "Developer workspace resolved via explicit env var MINERVA_WORKSPACE_ID. Developer runs `minerva register` which prints the workspace ID, then sets it in config."
  implication: The OSS workflow expects register to CREATE the workspace if it doesn't exist

## Resolution

root_cause: At register.py:89, when workspace is not found, it raises ValueError instead of creating the workspace. The design intent from phase 03.3 requires that when MINERVA_WORKSPACE_ID is explicitly set, register should create that workspace if it doesn't exist.
fix: Modified lines 80-114 to create workspace with the specified UUID when it doesn't exist, reusing the workspace creation logic from lines 137-169
verification: Code review confirms workspace is now created with the explicit MINERVA_WORKSPACE_ID when not found
files_changed:
  - src/cli/commands/register.py: Modified _resolve_workspace_id() to create workspace when MINERVA_WORKSPACE_ID is set but workspace doesn't exist
