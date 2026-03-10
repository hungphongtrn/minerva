# Planning Commits

Use this format after `/harvest-plan` finishes a bean plan.

## Format

- Type: `docs(plans)`
- Subject: `create plan for <bean-title>`
- Body: describe what the plan covers and the key decisions it records
- Footer: `Refs: <bean-id>`

## Example

```text
docs(plans): create plan for runtime session sync

Capture the implementation path, touched files, and verification steps for
session state persistence before coding starts.

Refs: bean-123
```
