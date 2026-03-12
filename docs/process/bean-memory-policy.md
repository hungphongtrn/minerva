# Bean Memory Policy

Beans are not only issue trackers. In Minerva, they are also the operational memory layer for stateless coding-agent sessions.

Canonical docs under `docs/` hold durable truth. Beans hold the current execution state needed to resume work from a fresh context.

## Why This Exists

LLM sessions are stateless by default. Chat history is transient and personal memory is incomplete. A fresh session should be able to recover active work by reading the relevant bean plus its linked docs.

## Core Rule

Create a bean as soon as work crosses from conversation into recoverable execution state.

Recoverable execution state means all of the following are true:
- there is a concrete objective
- there is progress or planned progress worth preserving
- the work may continue across sessions or need handoff
- a fresh agent would benefit from seeing the current state

## When a Bean Is Required

Create or reuse a bean when any of these are true:

1. The work may continue across sessions
- feature work
- bug investigation
- refactors
- documentation changes
- research or design work that may shape future implementation

2. The work changes repository state
- code
- docs
- tests
- config
- scripts
- process guidance

3. The work has multiple meaningful steps
- investigate -> decide -> implement
- research -> plan -> execute
- compare options -> update docs -> follow up

4. The work may create a durable decision
- architecture direction
- scope change
- process change
- user-approved policy

5. The work may need handoff to another session or another agent

## When a Bean Is Optional

You may start without a bean for:
- exploratory debugging
- open-ended research
- loose brainstorming
- a quick read-only inspection

But create a bean immediately if the work expands into a recoverable execution state.

## When a Bean Is Usually Not Needed

A bean is usually not needed for:
- pure explanation with no follow-up work
- a single-turn factual answer
- tiny read-only checks with no lasting significance

If the work later produces a task, decision, or follow-up, create a bean at that point.

## Reuse vs Create a New Bean

Reuse the current bean when:
- the objective is still the same
- the same acceptance criteria still apply
- the work is a continuation of the same execution thread

Create a new bean when:
- the objective changes materially
- a new independent deliverable appears
- a side investigation becomes substantial on its own
- follow-up work is useful but not required to finish the current bean
- the original bean would become confusing if it tracked both efforts

Rule of thumb:
One bean should answer one clear question about why the work exists.

## Bean Requirements for Fresh-Session Recovery

Every active bean should carry enough context for a fresh session to resume the work.

Required sections:
- `## Objective`
- `## Current Status`
- `## Governing Docs`
- `## Checklist`
- `## Latest Findings`
- `## Next Action`
- `## Blockers`

Required expectations:
- objective states the concrete outcome
- current status summarizes where the work stands right now
- governing docs link to the canonical docs that constrain the work
- checklist tracks the remaining execution steps
- latest findings capture high-signal discoveries only
- next action gives the most likely next step for a fresh session
- blockers are explicit, even when the value is `None`

Completed or scrapped beans must also include:
- `## Summary of Changes` for completed beans
- `## Reasons for Scrapping` for scrapped beans

## Session Start Habit

Before doing non-trivial work:
1. run `beans prime`
2. find the relevant bean or create one
3. read the bean before diving into implementation
4. use the linked docs to recover the governing context

## Session End Habit

Before pausing or ending a session:
1. update the checklist
2. update current status
3. record major findings or decisions
4. record blockers if any
5. set the next action

A paused session is not properly handed off until the bean is left in a re-enterable state.

## Promotion Rule

Beans are operational memory, not the final home of durable truth.

If work inside a bean changes long-lived truth, promote that truth before closing the bean by updating:
- canonical docs such as `docs/PROJECT.md`, `docs/architecture/**`, `docs/api/**`, `docs/process/**`, or ratified `docs/specs/**`
- `docs/DECISIONS.md` for meaningful decisions and approved direction changes

## Minimum Recovery Standard

A task is properly tracked only if a fresh agent can resume it from the bean plus linked docs without needing the original chat.
