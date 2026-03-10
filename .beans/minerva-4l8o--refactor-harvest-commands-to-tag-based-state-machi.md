---
# minerva-4l8o
title: Refactor harvest commands to tag-based state machine
status: completed
type: task
priority: high
tags:
    - harvest-system
created_at: 2026-03-09T16:57:24Z
updated_at: 2026-03-09T17:12:59Z
---

Refactor /harvest-plan, /harvest-implement, /harvest-check to use tags (planned, implemented, verified) as workflow state markers instead of relying on status + tasks.md re-parsing. Fixes the broken fix loop where /harvest-plan tried to recreate all beans from tasks.md.

## Summary of Changes

Restructured all harvest workflow files to follow progressive disclosure:

- **Created** `harvest-tags.md` — shared tag state machine reference (64 lines)
- **Slimmed commands**: plan.md (229→64), implement.md (150→54), check.md (151→54)
- **Updated skills**: all 3 reference `harvest-tags.md` instead of duplicating tag docs
- **Updated** `harvest-system.md` documentation with tag-based flow
- **Fixed** plan.md description: beans-first, not parse-first
- **Total**: 1179 → 823 lines (~30% reduction, zero duplication)
