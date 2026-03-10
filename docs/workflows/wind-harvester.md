# Wind Harvester

`wind-harvester` packages the full harvest workflow for OpenCode.

## Package Layout

```text
wind-harvester/
  bin/install.js
  src/
    command/harvest/
      bootstrap.md
      plan.md
      implement.md
      check.md
      status.md
    skills/harvest/
      harvest-bootstrap/
      harvest-plan/
      harvest-implement/
      harvest-check/
      harvest-commit/
      harvest-status/
    windmill/
      README.md
      harvest/
        bootstrap/
        commit/
        planning/
        implementation/
        verification/
        workflow/
```

## Workflow Coverage

`wind-harvester` packages the full harvest loop:

1. `/harvest-bootstrap` prepares docs, OpenSpec, Beans, milestones, and epics.
2. `/harvest-plan` turns unplanned work into plan docs.
3. `/harvest-implement` executes planned beans and records per-bean commit guidance.
4. `/harvest-check` verifies results, creates fix beans when needed, and surfaces loop boundaries.
5. `/harvest-status` renders a read-only dashboard from bean tags and session state.

Supporting references live under `wind-harvester/src/windmill/harvest/`:

- `bootstrap/`: setup flow, doc template rules, and roadmap-to-milestone mapping.
- `commit/`: per-command commit formats and timing rules.
- `workflow/`: session state, status formatting, doc sync, and archive sync references.
- `planning/`, `implementation/`, `verification/`: deeper execution guidance for the thin command and skill entry points.

## Progressive Disclosure

- `command/harvest/*.md` stays thin and only covers orchestration.
- `skills/harvest/*/SKILL.md` stays thin and only covers invocation.
- `windmill/harvest/` stores the deeper parsing rules, prompts, templates, commit rules, and verification rules that commands and skills reference.

## Installer

Run the installer with:

```bash
node wind-harvester/bin/install.js
```

For automation or verification, the installer also supports flags:

```bash
node wind-harvester/bin/install.js --target local --scope all --force
```

Targets:

- `local`: `./.opencode`
- `global`: `~/.config/opencode`, with fallback to the legacy `~/.config/.opencode`

The installer auto-discovers files under `src/command/`, `src/skills/`, and `src/windmill/`, so new packaged markdown assets do not require installer changes.

## Installed OpenCode Layout

```text
.opencode/
  command/harvest/
  skills/harvest/
  windmill/
    README.md
    harvest/
      bootstrap/
      commit/
      planning/
      implementation/
      verification/
      workflow/
```

The installer rewrites command and skill path placeholders so the installed assets point to the local `windmill` and `skills` copies instead of the repository source tree.

Bootstrap templates ship under `.opencode/windmill/harvest/bootstrap/templates/` for reuse by `/harvest-bootstrap`, but they are packaged source assets rather than user-editable workspace docs.
