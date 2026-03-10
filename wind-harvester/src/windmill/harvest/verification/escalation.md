# Escalation And Epic Completion

## Escalation

- First failure: create a fix bean and send the work back through `/harvest-plan`.
- Second failure on the same original bean: stop the loop and escalate to the user.

## Epic Completion

Complete the harvest epic only when every non-epic child bean has the `verified` tag.

After epic completion, suggest:

1. `/opsx-verify`
2. `/opsx-archive`
