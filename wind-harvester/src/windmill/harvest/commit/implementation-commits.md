# Implementation Commits

Use this format after `/harvest-implement` finishes a bean.

## Format

- Type: `feat`, `fix`, or `refactor`, based on the bean's actual change type
- Scope: derive from the main module, layer, or package changed
- Subject: imperative and 50 characters or fewer
- Body: explain what changed and why
- Footer: `Refs: <bean-id>`

## Granularity Rules

- Keep refactors separate from behavior changes when possible.
- Avoid bundling unrelated config churn into the same commit.
- Prefer one architectural layer per commit unless the bean explicitly spans layers.

## Examples

```text
feat(workflow): persist harvest session state

Save command progress into the change directory so status reporting and command
handoff can resume without manual reconstruction.

Refs: bean-123
```

```text
fix(check): stop infinite verification loops

Surface loop boundary options to the user after repeated failures so the
workflow does not keep generating more fix work without direction.

Refs: bean-456
```

```text
refactor(status): simplify dashboard references

Restructure the status output docs so command entry points stay thin while the
format rules live in the workflow reference layer.

Refs: bean-789
```
