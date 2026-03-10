# Roadmap To Milestones

Use `docs/roadmap/README.md` as the single source for initial Beans milestone creation.

## Parsing Rules

- Each `## Phase` heading becomes one Beans milestone.
- Each top-level bullet under a phase becomes one epic bean under that milestone.
- Preserve the roadmap order so milestone sequencing reflects dependency order.
- Ignore nested bullets unless the command is later extended to create task beans.

## Creation Rules

- Create milestones before epics.
- Use idempotent lookups so existing milestones and epics are reused.
- Keep epic titles close to the roadmap bullet text.
- Store enough description on the created bean to keep the roadmap traceable.

## Suggested CLI Flow

```bash
beans create --json "Phase 1: Foundation" -t milestone -s todo
beans create --json "Stand up the runtime shell" -t epic -s todo --parent <milestone-id>
```

## Notes

- If the roadmap is missing phase headings, stop and ask the user to normalize the file first.
- If a phase has no bullets, create no epics for that phase and report the gap.
