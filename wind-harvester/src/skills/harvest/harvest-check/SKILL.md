---
name: harvest-check
description: Verify implemented harvest beans by spawning smart-coder subagents. Use when invoking /harvest-check.
license: MIT
compatibility: Requires beans CLI and the smart-coder agent in OpenCode.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Check

This skill is the thin entry point for harvest verification.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Verification dimensions**: see `{{WINDMILL_ROOT}}/verification/check-dimensions.md`
> **Fix bean rules**: see `{{WINDMILL_ROOT}}/verification/fix-beans.md`
> **Escalation and epic completion**: see `{{WINDMILL_ROOT}}/verification/escalation.md`

Use this skill to:

- verify each implemented bean against its plan and summary
- append verification notes to the original bean
- create traceable fix beans without the `planned` tag
- complete the harvest epic only when all task beans are verified
