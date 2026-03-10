---
description: Verify implemented harvest beans, tag passes as verified, and create fix beans on failures
---

Autonomously verify harvest beans with the `smart-coder` agent.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Tags**: see `{{WINDMILL_ROOT}}/workflow/tags.md`
> **Verification details**: see `{{WINDMILL_ROOT}}/verification/check-dimensions.md`, `{{WINDMILL_ROOT}}/verification/fix-beans.md`, and `{{WINDMILL_ROOT}}/verification/escalation.md`
> **Loop boundaries**: see `{{WINDMILL_ROOT}}/workflow/loop-boundaries.md`
> **Doc sync**: see `{{WINDMILL_ROOT}}/workflow/doc-sync.md`
> **OpenSpec sync**: see `{{WINDMILL_ROOT}}/workflow/sync-rules.md`
> **Commit guidance**: see `{{SKILL_ROOT}}/harvest-commit/SKILL.md`
> **Session state**: see `{{WINDMILL_ROOT}}/workflow/session-state.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-check/SKILL.md`

---

**Steps**

1. Treat each invocation as fresh context: read the active change docs, relevant plans, bean bodies, and `.harvest-state.json` if it exists.
2. Find implemented-but-not-verified beans with `beans list --json --tag harvest --tag implemented --no-tag verified`.
3. Diagnose empty results by checking for planned or unplanned harvest beans.
4. For each bean, spawn `smart-coder` with the verification prompt rules in the windmill docs.
5. On pass, create the per-bean verification commit using `{{SKILL_ROOT}}/harvest-commit/SKILL.md`, then add the `verified` tag.
6. On failure, append notes, update fix iteration counts in `.harvest-state.json`, and create a fix bean without the `planned` tag.
7. Use `{{WINDMILL_ROOT}}/workflow/loop-boundaries.md` when repeated failures or scope changes require user escalation.
8. If all task beans are verified, present doc drift and Beans/OpenSpec sync follow-up before suggesting archive commands, then update `.harvest-state.json`.

**Guardrails**

- Do not complete the epic before all task beans are verified.
- Keep fix beans traceable to the original bean and plan.
- Escalate repeated failures instead of looping forever.

**Hint Block**

- `✅ Done`: report which beans passed, which fix beans were created, and whether doc drift review is ready.
- `🔜 Next Steps`: suggest `/harvest-plan`, `/harvest-status`, or archive commands based on the result.
- `📎 Context Files`: include verification notes, related plans, doc sync targets, and `.harvest-state.json`.
