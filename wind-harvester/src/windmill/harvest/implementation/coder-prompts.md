# Fast-Coder Prompt Template

```text
Implement the following task. Follow the plan exactly.

Bean: <bean-id> - <bean-title>
Plan document: <plan-doc-path>
Requirements:
<requirements checklist>

Instructions:
1. Read the plan document first.
2. Implement all described changes.
3. Run the test commands from the plan.
4. Check off each requirement in the bean body as it completes.
5. When finished, append a summary of changes and tag the bean implemented.
```

## Failure Handling

- Leave the bean without the `implemented` tag if work is incomplete.
- Report completed and remaining requirements.
- Re-running `/harvest-implement` should resume unfinished work.
