# Verification Commits

Use these formats after `/harvest-check` produces verification output.

## Verification Notes

- Type: `docs(verify)`
- Subject: `add verification notes for <bean-title>`
- Footer: `Refs: <bean-id>`

## Fix Bean Creation

- Type: `chore(harvest)`
- Subject: `create fix bean for <bean-title>`
- Footer: `Refs: <bean-id>`

## Examples

```text
docs(verify): add verification notes for runtime session sync

Record passing checks and remaining risks so archive review has a durable trail.

Refs: bean-123
```

```text
chore(harvest): create fix bean for runtime session sync

Capture the failed verification details and route the work back through the
planning loop with a traceable follow-up bean.

Refs: bean-123
```
