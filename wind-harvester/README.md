# wind-harvester

`wind-harvester` packages the harvest workflow for OpenCode.

## Contents

- `src/command/harvest/`: installable `/harvest-*` command entry points
- `src/skills/harvest/`: installable harvest skills
- `src/windmill/`: shared harvest references, prompts, and templates
- `bin/install.js`: interactive installer for OpenCode global or local targets

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
