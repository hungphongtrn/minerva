---
description: Implement planned harvest beans by priority tier and tag them as implemented
---

Autonomously implement harvest beans with the `fast-coder` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Execution details**: see `{{WINDMILL_ROOT}}/implementation/execution-model.md` and `{{WINDMILL_ROOT}}/implementation/coder-prompts.md`
> **Commit guidance**: see `{{SKILL_ROOT}}/harvest-commit/SKILL.md`
> **Session state**: see `{{WINDMILL_ROOT}}/workflow/session-state.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-implement/SKILL.md`

---

**Steps**

1. Treat each invocation as fresh context: read the active change docs, relevant plans, bean bodies, and `.harvest-state.json` if it exists.
2. Find planned-but-not-implemented beans with `beans list --json --tag harvest --tag planned --no-tag implemented`.
3. Diagnose empty results by checking for unplanned or unverified harvest beans.
4. Group ready beans by priority tier and run same-tier work in parallel.
5. After each successful implementation, create the per-bean implementation commit using `{{SKILL_ROOT}}/harvest-commit/SKILL.md`, then run `beans update --json <bean-id> --tag implemented -s completed`.
6. Update `.harvest-state.json` with the active change, recent implementation handoff, and last command metadata.

**Guardrails**

- Never start a lower tier before higher tiers finish.
- Skip beans without a plan link.
- Each subagent reads the plan doc first.
- Commit code and bean updates together.

**Hint Block**

- `✅ Done`: report which beans were implemented and which commits were created.
- `🔜 Next Steps`: suggest `/harvest-check` for the implemented beans.
- `📎 Context Files`: include the plan docs, touched change docs, and `.harvest-state.json`.
