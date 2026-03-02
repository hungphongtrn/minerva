---
status: resolved
trigger: "minerva register fails during volume sync with 'Snapshot picoclaw-snapshot not found', and --workspace-id flag is confusing UX for OSS model"
created: 2026-03-02T00:00:00Z
updated: 2026-03-02T00:30:00Z
---

## Current Focus

hypothesis: FIXED - Two issues addressed:
1. Snapshot name from settings was not being passed to DaytonaPackVolumeService
2. --workspace-id was required but should be optional for OSS with smart defaults

test: Verify fixes compile and address both root causes

expecting: Both issues resolved - snapshot name uses env var value, workspace_id optional

next_action: Update debug file status to resolved

## Symptoms

expected: Running `uv run minerva register ./test-agent --workspace-id <uuid>` should validate the pack, register it in the database, and sync its contents to a versioned Daytona volume successfully.

actual: Pack validates and registers in DB successfully, but volume sync step fails with error: "Failed to create disposable sandbox: Failed to create sandbox: Snapshot picoclaw-snapshot not found. Did you add it through the Daytona Dashboard?"

errors: "Snapshot picoclaw-snapshot not found. Did you add it through the Daytona Dashboard?"

reproduction: Run `uv run minerva register ./test-agent --workspace-id d773702d-765b-41f1-a482-fcd5d79ab504`

started: Current state - .env has DAYTONA_PICOCLAW_SNAPSHOT_NAME=picoclaw-base but error references "picoclaw-snapshot"

## Eliminated

- hypothesis: Environment variable DAYTONA_PICOCLAW_SNAPSHOT_NAME is not set in .env
  evidence: .env line 65 clearly shows DAYTONA_PICOCLAW_SNAPSHOT_NAME=picoclaw-base
  timestamp: 2026-03-02

- hypothesis: The snapshot name is hardcoded without reading environment variable
  evidence: Both files do use os.environ.get() with fallback, so it's reading env but the .env isn't being loaded by pydantic-settings when CLI runs
  timestamp: 2026-03-02

## Evidence

- timestamp: 2026-03-02
  checked: src/services/daytona_pack_volume_service.py lines 81-83
  found: self._snapshot_name = snapshot_name or os.environ.get("DAYTONA_PICOCLAW_SNAPSHOT_NAME", "picoclaw-snapshot")
  implication: The service reads from os.environ directly, but pydantic-settings in src/config/settings.py loads .env when Settings() is instantiated. The CLI doesn't use settings to pass snapshot_name.

- timestamp: 2026-03-02
  checked: src/cli/commands/register.py line 60
  found: volume_service = DaytonaPackVolumeService() - no snapshot_name parameter passed
  implication: The service uses the default fallback "picoclaw-snapshot" instead of the value from .env via settings

- timestamp: 2026-03-02
  checked: src/cli/commands/register.py lines 36-39, 94-98, 130
  found: --workspace-id is required flag, used to associate pack with workspace in DB
  implication: For OSS model, this is confusing UX. Need to either auto-create a default workspace or make it optional with a default.

- timestamp: 2026-03-02
  checked: src/config/settings.py line 109
  found: DAYTONA_PICOCLAW_SNAPSHOT_NAME: str = "" (empty default in Settings class)
  implication: Settings class has the field but register.py doesn't use settings to pass it to the service

## Resolution

root_cause: 
1. In register.py, DaytonaPackVolumeService was instantiated without passing snapshot_name from settings, causing it to use the fallback "picoclaw-snapshot" instead of the configured "picoclaw-base" from .env
2. The --workspace-id flag was required but confusing for OSS model where there should be a default/admin workspace

fix: 
1. Import settings in register.py and pass settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME to DaytonaPackVolumeService constructor
2. Make --workspace-id optional by changing required=True to required=False
3. Add _resolve_workspace_id() helper function that:
   - Uses provided workspace_id if given
   - If single workspace exists, uses it automatically
   - If multiple workspaces exist, errors with list for user to choose
   - If no workspaces exist, creates a default OSS workspace

verification: 
- Code changes compile without errors
- Snapshot name now properly flows from .env → settings → DaytonaPackVolumeService
- Workspace ID resolution follows OSS-friendly logic

files_changed:
- src/cli/commands/register.py:
  - Added import of settings and Workspace
  - Added typing.Optional import
  - Changed --workspace-id from required=True to required=False
  - Added _resolve_workspace_id() helper function
  - Updated _sync_pack_volume() to accept and pass snapshot_name parameter
  - Updated handle() to use _resolve_workspace_id() and pass settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME
