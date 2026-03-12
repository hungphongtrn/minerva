---
# minerva-pd1d
title: Migrate latest wind-harvester changes into Minerva
status: completed
type: feature
priority: high
created_at: 2026-03-10T08:17:30Z
updated_at: 2026-03-10T08:20:24Z
---

Apply the current `wind-harvester/` package updates into the active Minerva workspace, including matching command docs, harvest skills, and supporting workflow documentation where applicable.

## Tasks
- [x] Inspect latest `wind-harvester/` changes and map them to existing Minerva files
- [x] Port matching command, skill, and doc updates into Minerva
- [x] Run targeted verification for migrated artifacts
- [x] Add summary of changes

## Summary of Changes

Synced the local `.opencode/` harvest install from `wind-harvester/`, which added the packaged bootstrap, status, and commit assets plus the newer plan, implement, check, and workflow references. Updated `docs/workflows/harvest-system.md`, `docs/workflows/wind-harvester.md`, and `docs/INDEX.md` so the repository docs match the packaged flow, installer behavior, session-state usage, and installed OpenCode layout. Verified the migration by reinstalling `wind-harvester` into the local OpenCode target, confirming the new command and skill directories exist, and checking that placeholder tokens were fully rewritten out of `.opencode/`.
