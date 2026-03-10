---
description: Implement planned harvest beans by priority tier and tag them as implemented
---

Autonomously implement harvest beans with the `fast-coder` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Execution details**: see `{{WINDMILL_ROOT}}/implementation/execution-model.md` and `{{WINDMILL_ROOT}}/implementation/coder-prompts.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-implement/SKILL.md`

---

**Steps**

1. Find planned-but-not-implemented beans with `beans list --json --tag harvest --tag planned --no-tag implemented`.
2. Diagnose empty results by checking for unplanned or unverified harvest beans.
3. Group ready beans by priority tier and run same-tier work in parallel.
4. After each successful implementation, run `beans update --json <bean-id> --tag implemented -s completed`.
5. Report completed work and suggest `/harvest-check`.

**Guardrails**

- Never start a lower tier before higher tiers finish.
- Skip beans without a plan link.
- Each subagent reads the plan doc first.
- Commit code and bean updates together.
