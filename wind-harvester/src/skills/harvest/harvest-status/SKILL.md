---
name: harvest-status
description: Display a read-only harvest dashboard from session state and bean tags. Use when invoking /harvest-status.
license: MIT
compatibility: Requires beans CLI and access to the active OpenSpec change.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Status

This skill is the thin entry point for harvest status display.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Session state**: see `{{WINDMILL_ROOT}}/workflow/session-state.md`
> **Status format**: see `{{WINDMILL_ROOT}}/workflow/status-format.md`

Use this skill to:

- inspect the active change without mutating it
- combine bean tag state with `.harvest-state.json`
- report the next likely command and relevant file paths
