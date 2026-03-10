# Harvest Session State

Harvest commands use a lightweight state file to preserve context between `/harvest-*` runs.

## Location

- `openspec/changes/<change-name>/.harvest-state.json`

## Schema

```json
{
  "change": "add-status-command",
  "epicBean": "bean-123",
  "fixIterations": {
    "bean-456": 1
  },
  "userDecisions": [
    {
      "at": "2026-03-10T08:00:00Z",
      "context": "loop-boundary",
      "choice": "create-fix-bean",
      "notes": "Keep scope unchanged"
    }
  ],
  "lastCommand": "harvest-check",
  "lastCommandAt": "2026-03-10T08:00:00Z"
}
```

## Read Rules

- Each command reads the file on entry.
- Missing state is allowed and means the workflow is on its first run.
- Commands should treat the state file as advisory context, not a replacement for reading change docs and beans.

## Write Rules

- Each command updates the file after it completes its main work.
- Preserve existing decision history unless the user explicitly wants it pruned.
- Update `lastCommand` and `lastCommandAt` on every successful run.

## Uses

- `/harvest-plan`: store the active change and epic bean.
- `/harvest-implement`: store the most recent implementation handoff.
- `/harvest-check`: store fix iteration counts and user loop decisions.
- `/harvest-status`: render dashboard context without mutating anything.
