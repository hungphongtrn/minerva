# Planner Prompts And Plan Templates

## Regular Task Prompt

```text
Create a detailed implementation plan for this task.

Bean: <bean-id> - <bean-title>
Requirements:
<requirements checklist>

Read:
- openspec/changes/<name>/proposal.md
- openspec/changes/<name>/design.md
- relevant docs/

Treat the task as fresh context every time. Re-read source docs and bean details even when resuming prior work.

Write the plan to docs/plans/<change-name>/<section-slug>.md.

The plan must include:
1. Problem statement and goal
2. File-level changes
3. Key interfaces and types
4. Test strategy and commands
5. Dependencies
6. References consulted
```

## Fix Prompt

```text
Create a fix plan for this bug.

Fix Bean: <bean-id> - <bean-title>
Problem: <problem>
Expected: <expected>
Actual: <actual>
Original Bean: <original bean>

Write the fix plan to docs/plans/<change-name>/fix-<slug>.md.

The fix plan must include:
1. Root cause
2. Minimal file changes
3. Test updates
4. Verification steps

Before tagging the bean planned, prepare the per-bean planning commit.
```

## Plan Completion Rule

Only tag a bean `planned` after the plan doc exists and the bean links to it.
