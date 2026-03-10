---
# minerva-u5qd
title: Extend wind-harvester plan with installer flow
status: completed
type: task
priority: normal
created_at: 2026-03-09T18:05:54Z
updated_at: 2026-03-09T18:06:01Z
---

Add the installer and path-rewrite planning details for the wind-harvester package.

## Todo
- [ ] Define install script scope for OpenCode-only support
- [ ] Plan global vs local install targets and path rewriting
- [x] Update the package plan to keep commands and skills progressively disclosed

## Summary of Changes

Expanded the wind-harvester plan to include an OpenCode-only interactive installer at `bin/install.js`, with support for global and local `.opencode` targets, path rewriting for installed assets, and retention of progressive disclosure across command and skill entry points.
