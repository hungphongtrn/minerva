# Harvest Tag State Machine

Each command advances the workflow by adding tags to beans.

## Tags

| Tag | Added by | Meaning |
| --- | --- | --- |
| `harvest` | `/harvest-plan` | Bean belongs to the harvest workflow |
| `<change-name>` | `/harvest-plan` | Bean belongs to a specific OpenSpec change |
| `planned` | `/harvest-plan` | Plan doc exists and the bean is ready for coding |
| `implemented` | `/harvest-implement` | Code exists and is ready for verification |
| `verified` | `/harvest-check` | Verification passed |
| `fix` | `/harvest-check` | Bean was created from a failed verification |

## Queries

```bash
beans list --json --tag harvest --no-tag planned
beans list --json --tag harvest --tag planned --no-tag implemented
beans list --json --tag harvest --tag implemented --no-tag verified
```

## Contracts

- `/harvest-plan`: add `planned` and set status to `todo`
- `/harvest-implement`: add `implemented` and set status to `completed`
- `/harvest-check`: add `verified` on pass, or create a `fix` bean on failure
