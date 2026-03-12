---
# minerva-0qt4
title: Shift project process from spec plugins to markdown-plus-beans workflow
status: completed
type: task
priority: normal
created_at: 2026-03-11T08:11:52Z
updated_at: 2026-03-11T08:16:55Z
---

## Objective
Document and align the project workflow around markdown documents with progressive disclosure, AGENTS.md guidance, and beans-only issue tracking instead of specification plugins.

## Tasks
- [x] Review current docs for specification-plugin references and project workflow expectations
- [x] Update docs to describe the markdown-plus-beans workflow and remove conflicting guidance
- [x] Record the user decision in docs/DECISIONS.md
- [x] Summarize changes and next implications

## Summary of Changes
- Removed OpenSpec/plugin workflow guidance from `AGENTS.md` and standardized on markdown documents plus beans.
- Added `docs/process/INDEX.md` and `docs/process/markdown-beans-workflow.md` to document the idea -> MVP -> phase -> task loop and required task document bundle.
- Updated `docs/INDEX.md`, `docs/specs/INDEX.md`, and existing orchestrator plan references to point at in-repo markdown docs instead of OpenSpec artifacts.
- Logged the process decision in `docs/DECISIONS.md`.
