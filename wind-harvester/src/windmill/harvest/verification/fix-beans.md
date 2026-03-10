# Fix Bean Rules

When verification fails, append failure notes to the original bean and create a fix bean.

## Fix Bean Body

```markdown
## Problem

<specific failure>

## Expected

<expected behavior>

## Actual

<actual behavior>

## Original Bean

- **Bean**: <bean-id> - <title>
- **Plan**: <plan doc>

## Fix Requirements

- [ ] <fix action>
```

## Rules

- Keep one fix bean per distinct failure.
- Tag the bean with `harvest`, `<change-name>`, and `fix`.
- Do not add `planned` when creating the fix bean.
- Keep the original bean and plan link in the fix bean body.
