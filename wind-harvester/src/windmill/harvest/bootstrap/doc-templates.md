# Harvest Doc Templates

Bootstrap ships a fixed set of project entry-point docs.

## Required Templates

- `docs/project/README.md`
- `docs/architecture/README.md`
- `docs/coding-standards/README.md`
- `docs/roadmap/README.md`
- `docs/research/README.md`

## Folder-First Convention

- Always create docs as `docs/<topic>/README.md`.
- Never create top-level topic files such as `docs/PROJECT.md` or `docs/ROADMAP.md`.
- Reference links should always point to the stable `README.md` entry point.

## Growth Rules

- Decompose a doc when it grows past 300 lines.
- Decompose a doc when it grows beyond 5 major sections.
- Keep the entry-point `README.md` as the index and move deep detail into sibling files.

## Decomposition Pattern

1. Keep `README.md` as the durable entry point.
2. Move detailed material into focused files such as `execution-flow.md` or `state-machines.md`.
3. Replace moved sections with a short summary and relative links.
4. Update cross-references so callers still land on `README.md` first.

## Guidance Comments

- Templates may include HTML comments like `<!-- Fill: summarize the current product and target users. -->`.
- Guidance comments help the user fill the doc but should be removed or replaced as real content is written.
