---
# minerva-gsda
title: Implement wind-harvester improvements
status: completed
type: feature
priority: high
created_at: 2026-03-10T08:06:20Z
updated_at: 2026-03-10T08:12:14Z
---

Execute docs/plan.md and docs/task.md for wind-harvester improvements.

## Tasks
- [x] Create bootstrap reference docs and templates
- [x] Add bootstrap command and skill
- [x] Add commit reference docs and commit skill
- [x] Add workflow docs for session state, loop boundaries, status format, doc sync, and sync rules
- [x] Update harvest commands with commit guidance, session state, and hint blocks
- [x] Add harvest status command and skill
- [x] Update windmill and package READMEs plus prompt/escalation docs
- [x] Run structural verification commands
- [x] Update bean with summary of changes

## Summary of Changes

Implemented the harvest bootstrap, commit, session-state, loop-boundary, status, doc-sync, and Beans/OpenSpec sync docs and thin entry points across `src/command/`, `src/skills/`, and `src/windmill/`. Updated the existing plan, implement, and check commands plus workflow references, prompt docs, and package READMEs to add fresh-context guidance, per-bean commit hooks, standard hint blocks, and installer auto-discovery notes. Verified the package by listing all packaged markdown assets, running the installer against `/tmp/wind-harvester-verify-IH84zc`, checking placeholder rewriting, and validating internal placeholder references.
