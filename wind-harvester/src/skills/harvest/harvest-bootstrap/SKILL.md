---
name: harvest-bootstrap
description: Initialize project docs, OpenSpec, Beans, and roadmap milestones. Use when invoking /harvest-bootstrap.
license: MIT
compatibility: Requires beans CLI, openspec CLI, and filesystem access for doc templates.
metadata:
  author: minerva
  version: "0.4"
---

# Harvest Bootstrap

This skill is the thin entry point for harvest bootstrap.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Bootstrap overview**: see `{{WINDMILL_ROOT}}/bootstrap/overview.md`
> **Doc templates**: see `{{WINDMILL_ROOT}}/bootstrap/doc-templates.md`
> **Milestone creation**: see `{{WINDMILL_ROOT}}/bootstrap/milestone-creation.md`

Use this skill to:

- validate that the required project docs exist
- seed template docs into `docs/` when needed
- initialize OpenSpec and Beans only when they are missing
- create milestones and epics from `docs/roadmap/README.md`
