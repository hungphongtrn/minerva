---
description: Plan unplanned harvest beans by creating plans and tagging them as planned
---

Autonomously plan harvest beans with the `smart-planner` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Planning details**: see `{{WINDMILL_ROOT}}/planning/tasks-parsing.md`, `{{WINDMILL_ROOT}}/planning/bean-creation.md`, and `{{WINDMILL_ROOT}}/planning/planner-prompts.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-plan/SKILL.md`

---

**Steps**

1. Find unplanned beans with `beans list --json --tag harvest --no-tag planned`.
2. If none exist, inspect in-progress OpenSpec changes and parse `tasks.md` into epic and task beans.
3. For each unplanned bean, spawn `smart-planner` with the prompt rules in the windmill planning docs.
4. After each plan is written, run `beans update --json <bean-id> --tag planned -s todo`.
5. Report the planned beans and suggest `/harvest-implement`.

**Guardrails**

- Read `proposal.md` and `design.md` before creating beans.
- Keep bean bodies self-contained.
- Write plan docs before tagging a bean as `planned`.
- Re-running must stay idempotent.
