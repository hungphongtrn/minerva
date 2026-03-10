# Implementation Execution Model

## Readiness

A bean is ready when it:

1. has the `planned` tag
2. does not have the `implemented` tag
3. links to a plan doc
4. is not blocked by incomplete beans

## Priority Tiers

| Tier | Priorities | Rule |
| --- | --- | --- |
| 1 | `critical`, `high` | Run first |
| 2 | `normal` | Wait for tier 1 |
| 3 | `low`, `deferred` | Wait for tier 2 |

Same-tier work can run in parallel. Lower tiers wait for higher tiers to finish.

## Completion Rule

When implementation succeeds, add `implemented`, set status to `completed`, and append a summary of changes.
