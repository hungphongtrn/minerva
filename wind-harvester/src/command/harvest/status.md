---
description: Show a read-only harvest dashboard from bean tags and session state
---

Display harvest workflow progress without mutating project state.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Session state**: see `{{WINDMILL_ROOT}}/workflow/session-state.md`
> **Status format**: see `{{WINDMILL_ROOT}}/workflow/status-format.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-status/SKILL.md`

---

**Steps**

1. Detect the active change and read `openspec/changes/<change-name>/.harvest-state.json` when it exists.
2. Query related beans by harvest tags and summarize counts by state.
3. Read active plan file references from the bean bodies or session state.
4. Render the dashboard using the status format doc.

**Guardrails**

- Keep the command read-only.
- Fall back to bean tags when no session state file exists.
- Report missing context files explicitly instead of guessing.

**Hint Block**

- `✅ Done`: report the current dashboard snapshot.
- `🔜 Next Steps`: suggest the next harvest command based on the current state.
- `📎 Context Files`: include the state file, tasks file, and active plans.
