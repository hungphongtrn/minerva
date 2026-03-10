---
description: Plan unplanned harvest beans by creating plans and tagging them as planned
---

Autonomously plan harvest beans with the `smart-planner` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Planning details**: see `{{WINDMILL_ROOT}}/planning/tasks-parsing.md`, `{{WINDMILL_ROOT}}/planning/bean-creation.md`, and `{{WINDMILL_ROOT}}/planning/planner-prompts.md`
> **Commit guidance**: see `{{SKILL_ROOT}}/harvest-commit/SKILL.md`
> **Session state**: see `{{WINDMILL_ROOT}}/workflow/session-state.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-plan/SKILL.md`

---

**Steps**

1. Treat each invocation as fresh context: read the active change docs, relevant bean bodies, and `.harvest-state.json` if it exists.
2. Find unplanned beans with `beans list --json --tag harvest --no-tag planned`.
3. If none exist, inspect in-progress OpenSpec changes and parse `tasks.md` into epic and task beans.
4. For each unplanned bean, spawn `smart-planner` with the prompt rules in the windmill planning docs.
5. After each plan is written, create the per-bean planning commit using `{{SKILL_ROOT}}/harvest-commit/SKILL.md`, then run `beans update --json <bean-id> --tag planned -s todo`.
6. Update `.harvest-state.json` with the active change, epic bean, and last command metadata.

**Guardrails**

- Read `proposal.md` and `design.md` before creating beans.
- Keep bean bodies self-contained.
- Write plan docs before tagging a bean as `planned`.
- Re-running must stay idempotent.

**Hint Block**

- `✅ Done`: report which beans were planned and which plan docs were written.
- `🔜 Next Steps`: suggest `/harvest-implement` for the newly planned beans.
- `📎 Context Files`: include the plan docs, `tasks.md`, and `.harvest-state.json`.
