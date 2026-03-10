---
name: harvest-plan
description: Plan unplanned harvest beans by spawning smart-planner subagents. Use when invoking /harvest-plan.
license: MIT
compatibility: Requires beans CLI, openspec CLI, and the smart-planner agent in OpenCode.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Plan

This skill is the thin entry point for harvest planning.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Parsing rules**: see `{{WINDMILL_ROOT}}/planning/tasks-parsing.md`
> **Bean creation**: see `{{WINDMILL_ROOT}}/planning/bean-creation.md`
> **Planner prompts and plan templates**: see `{{WINDMILL_ROOT}}/planning/planner-prompts.md`

Use this skill to:

- discover unplanned harvest beans, including fix beans
- populate beans from `tasks.md` when none exist yet
- spawn `smart-planner` with the appropriate task or fix prompt
- mark beans `planned` only after the plan doc exists
