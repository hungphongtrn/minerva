---
name: harvest-commit
description: Apply per-bean commit rules after harvest plan, implement, or check work completes.
license: MIT
compatibility: Requires git and beans CLI.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Commit

This skill is the thin entry point for harvest commit guidance.

> **Commit rules**: see `{{WINDMILL_ROOT}}/commit/commit-rules.md`
> **Plan commits**: see `{{WINDMILL_ROOT}}/commit/plan-commits.md`
> **Implementation commits**: see `{{WINDMILL_ROOT}}/commit/implementation-commits.md`
> **Verification commits**: see `{{WINDMILL_ROOT}}/commit/verification-commits.md`

Use this skill after completing work in any `/harvest-*` command so each bean gets an atomic commit before tagging or archive follow-up.
