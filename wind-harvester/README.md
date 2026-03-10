# wind-harvester

`wind-harvester` packages the harvest workflow for OpenCode.

## Contents

- `src/command/harvest/`: installable `/harvest-bootstrap`, `/harvest-plan`, `/harvest-implement`, `/harvest-check`, and `/harvest-status` entry points
- `src/skills/harvest/`: packaged skills for bootstrap, planning, implementation, verification, commit guidance, and status reporting
- `src/windmill/`: shared reference docs, prompt templates, workflow rules, and bootstrap doc templates
- `bin/install.js`: interactive installer for OpenCode global or local targets

## Workflow

`wind-harvester` packages the full harvest loop:

1. `/harvest-bootstrap` prepares docs, OpenSpec, Beans, milestones, and epics.
2. `/harvest-plan` turns unplanned work into plan docs.
3. `/harvest-implement` executes planned beans and records per-bean commit guidance.
4. `/harvest-check` verifies results, creates fix beans when needed, and surfaces loop boundaries.
5. `/harvest-status` renders a read-only dashboard from bean tags and session state.

Supporting references live under `src/windmill/harvest/`:

- `bootstrap/`: setup flow, doc-template rules, and roadmap-to-milestone mapping
- `commit/`: per-command commit formats and commit timing rules
- `workflow/`: state, status, sync, and orchestration references
- `planning/`, `implementation/`, `verification/`: deeper execution guidance for the thin command and skill entry points

## Install

Run the installer from the repository root:

```bash
node wind-harvester/bin/install.js
```

For automation or verification, the installer also supports flags:

```bash
node wind-harvester/bin/install.js --target local --scope all --force
```

Targets:

- `local`: `./.opencode`
- `global`: OpenCode config under `~/.config/opencode` or the legacy `~/.config/.opencode`

The package only supports OpenCode for now.

The installer auto-discovers files under `src/command/`, `src/skills/`, and `src/windmill/`, so new packaged markdown assets do not require installer changes.

Bootstrap templates live in `src/windmill/harvest/bootstrap/templates/`. They ship with the package for `/harvest-bootstrap` to copy into a project's `docs/` tree, but they are not intended to be edited directly in `.opencode/`.
