# Harvest Status Format

`/harvest-status` is a read-only dashboard for the active change.

## Output Sections

1. Change name and epic bean reference.
2. Per-state counts for `verified`, `implemented`, `planned`, `unplanned`, and fix beans.
3. Fix iteration tracker from `.harvest-state.json`.
4. Last action taken and the suggested next command.
5. File references for the active plans and the session state file.

## Suggested Layout

```text
Harvest Status

Change: add-status-command
Epic: bean-123 - Improve harvest workflow

Counts
- Verified: 2
- Implemented: 1
- Planned: 1
- Unplanned: 0
- Fix beans: 1

Fix Iterations
- bean-456: 1

Last Action
- harvest-check at 2026-03-10T08:00:00Z
- Next: /harvest-plan for bean-456

Context Files
- openspec/changes/add-status-command/tasks.md
- openspec/changes/add-status-command/.harvest-state.json
- docs/plans/add-status-command/status-dashboard.md
```

## Rules

- Do not mutate Beans or OpenSpec while rendering status.
- Prefer exact file paths over prose descriptions.
- If there is no state file yet, say so explicitly and fall back to bean tags.
