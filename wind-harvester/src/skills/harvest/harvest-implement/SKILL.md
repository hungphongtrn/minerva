---
name: harvest-implement
description: Implement planned harvest beans by spawning fast-coder subagents grouped by priority tier. Use when invoking /harvest-implement.
license: MIT
compatibility: Requires beans CLI and the fast-coder agent in OpenCode.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Implement

This skill is the thin entry point for harvest implementation.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Execution model**: see `{{WINDMILL_ROOT}}/implementation/execution-model.md`
> **Coder prompt**: see `{{WINDMILL_ROOT}}/implementation/coder-prompts.md`

Use this skill to:

- select beans that are planned and ready for coding
- execute by priority tier, with same-tier work in parallel
- follow the plan doc before editing code
- mark beans `implemented` only after requirements are complete
