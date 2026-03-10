# Wind Harvester

`wind-harvester` packages the harvest commands, skills, and shared support files for OpenCode.

## Package Layout

```text
wind-harvester/
  bin/install.js
  src/
    command/harvest/
    skills/harvest/
    windmill/harvest/
```

## Progressive Disclosure

- `command/harvest/*.md` stays thin and only covers orchestration.
- `skills/harvest/*/SKILL.md` stays thin and only covers invocation.
- `windmill/harvest/` stores the deeper parsing rules, prompts, templates, and verification rules that commands and skills reference.

## Installer

Run the installer with:

```bash
node wind-harvester/bin/install.js
```

It supports:

- `local` install into `./.opencode`
- `global` install into `~/.config/opencode`, with fallback to the legacy `~/.config/.opencode`

The installer can also run non-interactively with `--target`, `--scope`, `--force`, and `--yes`.

## Installed OpenCode Layout

```text
.opencode/
  command/harvest/
  skills/harvest/
  windmill/harvest/
```

The installer rewrites command and skill path placeholders so the installed assets point to the local `windmill` copy instead of the repository source tree.
