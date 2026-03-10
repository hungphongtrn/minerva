# Fast-Coder Prompt Template

```text
Implement the following task. Follow the plan exactly.

Bean: <bean-id> - <bean-title>
Plan document: <plan-doc-path>
Requirements:
<requirements checklist>

Instructions:
1. Read the plan document first.
2. Treat the task as fresh context and re-read any referenced docs before editing.
3. Implement all described changes.
4. Run the test commands from the plan.
5. Check off each requirement in the bean body as it completes.
6. Prepare the per-bean implementation commit before tagging the bean implemented.
7. When finished, append a summary of changes and tag the bean implemented.
```

## Failure Handling

- Leave the bean without the `implemented` tag if work is incomplete.
- Report completed and remaining requirements.
- Re-running `/harvest-implement` should resume unfinished work.
