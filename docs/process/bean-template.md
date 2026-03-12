# Bean Template for Agent Resumability

Use this structure for any bean that tracks non-trivial work.

```md
## Objective

Describe the concrete outcome this bean exists to produce.

## Current Status

Summarize the current state in 1-3 lines.
Examples:
- Investigating root cause in sandbox adapter
- Implementation is partially complete; repository layer is done, tests remain
- Waiting for user decision on API contract

## Governing Docs

List the canonical docs that constrain this work.
- [docs/PROJECT.md](../PROJECT.md)
- [docs/architecture/INDEX.md](../architecture/INDEX.md)
- [docs/process/INDEX.md](./INDEX.md)

## Checklist

- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

## Latest Findings

Capture only the highest-signal discoveries a fresh session must know.
- Finding 1
- Finding 2

## Next Action

State the next recommended action for a fresh session in one short paragraph or bullet.

## Blockers

- None
```

## Completed Bean Additions

Append this section before marking a bean completed:

```md
## Summary of Changes

Summarize what changed, what was verified, and any important follow-up context.
```

## Scrapped Bean Additions

Append this section before marking a bean scrapped:

```md
## Reasons for Scrapping

Explain why the work stopped and whether any follow-up bean should be created.
```

## Usage Notes

- Keep the template concise and high-signal.
- Link to canonical docs rather than copying large amounts of context into the bean.
- Update `## Current Status`, `## Latest Findings`, and `## Next Action` whenever a session pauses.
- If durable truth changes, update the relevant canonical docs and `docs/DECISIONS.md` before closing the bean.
