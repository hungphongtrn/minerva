---
description: Verify implemented harvest beans, tag passes as verified, and create fix beans on failures
---

Autonomously verify harvest beans with the `smart-coder` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Verification details**: see `{{WINDMILL_ROOT}}/verification/check-dimensions.md`, `{{WINDMILL_ROOT}}/verification/fix-beans.md`, and `{{WINDMILL_ROOT}}/verification/escalation.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-check/SKILL.md`

---

**Steps**

1. Find implemented-but-not-verified beans with `beans list --json --tag harvest --tag implemented --no-tag verified`.
2. Diagnose empty results by checking for planned or unplanned harvest beans.
3. For each bean, spawn `smart-coder` with the verification prompt rules in the windmill docs.
4. On pass, add the `verified` tag. On failure, append notes and create a fix bean without the `planned` tag.
5. If all task beans are verified, complete the epic and suggest archive commands.

**Guardrails**

- Do not complete the epic before all task beans are verified.
- Keep fix beans traceable to the original bean and plan.
- Escalate repeated failures instead of looping forever.
