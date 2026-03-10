# Beans And OpenSpec Sync Rules

Keep Beans and OpenSpec aligned before archive.

## Tasks Sync

- Update `openspec/changes/<change-name>/tasks.md` checkboxes to match the set of verified beans.
- Do not mark a task complete until the corresponding bean is verified.

## Design Notes Sync

- Append an implementation notes section to `design.md` when the shipped result diverges from the original design.
- Keep the note short and focused on the delta, reason, and user-visible impact.

## Timing

- Run this sync alongside the doc drift check.
- Finish the sync before suggesting `/opsx-archive`.
