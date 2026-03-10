---
# minerva-n4jd
title: Implement wind-harvester package and installer
status: completed
type: feature
priority: high
created_at: 2026-03-09T18:07:00Z
updated_at: 2026-03-09T18:21:45Z
---

Implement the wind-harvester package by moving harvest commands and skills into a packaged structure, applying progressive disclosure via a shared windmill folder, and adding an interactive OpenCode-only installer.

## Todo
- [x] Inspect current repo layout and packaging/runtime constraints for a JS installer
- [x] Create wind-harvester package structure with commands, skills, and windmill shared docs/templates
- [x] Refactor harvest commands and skills to use windmill progressive disclosure references
- [x] Implement bin/install.js for OpenCode global/local installation and path rewriting
- [x] Update related documentation for the new package and install flow
- [x] Verify the package layout and installer behavior

## Summary of Changes

Created the `wind-harvester` package with installable harvest commands, skills, and a shared `windmill` reference layer. Refactored both the packaged assets and the repository `.opencode` copies to use progressive disclosure, added the interactive OpenCode installer at `wind-harvester/bin/install.js`, updated workflow docs, and verified the installer by installing into a temporary local `.opencode` target and checking the rewritten links.
