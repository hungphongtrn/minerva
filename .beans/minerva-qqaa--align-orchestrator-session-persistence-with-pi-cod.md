---
# minerva-qqaa
title: Align orchestrator session persistence with pi coding agent reference
status: in-progress
type: feature
priority: high
created_at: 2026-03-11T09:19:56Z
updated_at: 2026-03-12T05:59:11Z
---

## Context
The user wants Minerva to follow the same overall approach as the pi coding agent reference repo while preserving current agent behavior.

## Requested Direction
- Keep agent behavior unchanged.
- Change session persistence to use Postgres.
- Keep tool execution running through the Daytona sandbox.
- Use the pi coding agent architecture as the reference point for the session model and orchestration flow.

## Discussion Scope
This bean is intended to start design discussion before implementation.

## Initial Questions
- Which pi coding agent session concepts should be mirrored exactly versus adapted for Minerva?
- What Postgres schema and migration strategy should back persisted sessions, branches, events, and tool state?
- How should Daytona sandbox lifecycle/state be linked to persisted sessions without changing agent behavior?
- What compatibility or migration plan is needed from the current state model?

## Definition of Ready
- [x] Review relevant pi coding agent session docs/code as the reference baseline
- [ ] Compare current Minerva orchestrator session flow to the reference approach
- [ ] Propose a Postgres-backed session model that preserves current behavior
- [ ] Define how Daytona sandbox execution remains the tool runtime layer
- [x] Agree on implementation boundaries before coding

## Discussion Artifacts
- Discussion conclusion: [docs/disussions/minerva-qqaa-pi-coding-agent-alignment.md](../docs/disussions/minerva-qqaa-pi-coding-agent-alignment.md)
- Discussion index: [docs/disussions/INDEX.md](../docs/disussions/INDEX.md)
- Research note: [docs/research/pi-coding-agent-sdk.md](../docs/research/pi-coding-agent-sdk.md)
- Decision log: [docs/DECISIONS.md](../docs/DECISIONS.md)

## Notes
- Session persistence should follow pi coding agent durable-entry behavior rather than persisting every streaming delta.
- v1 keeps branch-capable internals but does not expose branching in product UX.
- Runtime resources such as AGENTS.md and skills should be available inside the sandbox filesystem.
