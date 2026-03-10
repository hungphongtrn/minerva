# tasks.md Parsing Rules

Parse `openspec/changes/<name>/tasks.md` only when no unplanned harvest beans exist.

## Expected Shape

```markdown
## 1. Section Title

- [ ] 1.1 First requirement
- [ ] 1.2 Second requirement
```

## Rules

- A section starts at each `## N. Title` heading.
- Checklist items under that heading become the bean requirements.
- Nested checklist items stay attached to their parent requirement.
- Ignore prose that is not a section heading or checklist item.
- Preserve numbering from the source document.

## Inputs To Read First

- `openspec/changes/<name>/proposal.md`
- `openspec/changes/<name>/design.md`
- `openspec/changes/<name>/tasks.md`
