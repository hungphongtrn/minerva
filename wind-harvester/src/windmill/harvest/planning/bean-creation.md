# Bean Creation Rules

## Idempotency

Before creating a bean for a section, check whether it already exists:

```bash
beans list --json --tag harvest --tag "<change>" -S "title:<Section Title>"
```

- Existing bean with `planned`: skip it
- Existing bean without `planned`: queue it for planning
- No existing bean: create it

## Epic Bean

Create one epic bean per change. Include links to the change `proposal.md`, `design.md`, and `tasks.md`, plus a table of child task beans.

## Task Bean Body

Each task bean should include:

- `## Requirements`
- `## References`
- `## Plan`

The bean body must stay self-contained.

## Priority Mapping

- Sections `1-2`: `high`
- Sections `3-5`: `normal`
- Sections `6+`: `low`

## Dependency Detection

Use `--blocked-by` when a section explicitly depends on another section's types, interfaces, or setup work.
