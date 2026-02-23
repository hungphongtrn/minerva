# Picoclaw Multi-Tenant OSS Runtime

## What This Is

An open-source platform for running Picoclaw in distributed, multi-user environments with strong sandbox isolation and a simple API surface for product integration. v1 focuses on a self-hosted runtime teams can deploy in their own infrastructure and scale for many users and sessions. A later milestone will add a business-facing layer for rapid procedure distillation using skill packs and agent identity files.

## Core Value

Any team can run Picoclaw safely for multiple users with strong isolation and predictable behavior, without building orchestration and sandbox infrastructure themselves.

## Requirements

### Validated

(None yet - ship to validate)

### Active

- [ ] User can send an API request and run an agent in an isolated sandbox tied to that user workspace.
- [ ] Platform can resolve an existing active sandbox for a user or hydrate a new sandbox from the latest checkpoint.
- [ ] Platform streams typed runtime events to clients (message, tool call, tool result, UI patch, state update, error).
- [ ] Platform enforces workspace safety and isolation boundaries compatible with Picoclaw's filesystem-centric model.
- [ ] Platform persists event logs and session metadata, with milestone-based workspace checkpoint snapshots.
- [ ] Platform supports user-centric tenancy with one workspace per user shared across that user's sessions.

### Out of Scope

- Organization-first tenancy and enterprise billing abstractions - deferred until OSS runtime is stable and adopted.
- Full business procedure-distillation product UX - this is the post-v1 milestone after runtime foundation is proven.
- Fully managed hosted service by this team - v1 targets self-hosting operators.

## Context

- Existing reference implementation is Picoclaw, which is filesystem-centric for sessions and memory in a workspace model.
- User goal is to preserve Picoclaw semantics while enabling distributed multi-user deployment.
- Primary first success signal is production pilots running real workloads within 90 days.
- Team context: project owner is strongest in Python, teammates are stronger in Go; speed to market is prioritized.
- Target operator in v1 is engineering teams deploying in their own infrastructure.
- Canonical control/data flow direction: API request -> user identity resolution -> sandbox lookup -> route or hydrate from snapshot -> run -> stream events -> checkpoint milestones.

## Constraints

- **Timeline**: Time-to-market is primary - architecture must favor fast delivery to pilots.
- **Security**: Strong isolation required - sandbox boundary must prevent cross-user data leakage.
- **Tenancy model**: User-centric in v1 - one workspace per user, shared across user sessions.
- **Deployment**: Self-hosted first - avoid assumptions that require managed control plane operations.
- **Tech stack**: Python control plane plus Go runtime harness alignment - leverage existing Picoclaw patterns while moving quickly.
- **Persistence**: Event log plus metadata as authority, with milestone snapshots to object storage.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1 scope is OSS multi-tenant runtime first | Foundation must be stable before business-facing distillation platform | - Pending |
| User-centric tenancy in v1 | OSS adopters can map users to their own org model later | - Pending |
| One workspace per user shared across sessions | Matches Picoclaw FS-centric memory/session approach and simplifies user continuity | - Pending |
| Strong sandbox isolation using Daytona | Required safety boundary for multi-user execution | - Pending |
| Event stream envelope as canonical response model | Needed for rich outputs: messages, tool events, UI events, and state updates | - Pending |
| Milestone checkpoints instead of full periodic snapshots | Better cost and performance tradeoff while retaining recoverability | - Pending |
| Python control plane plus Go runtime harness | Balances team skill profile with compatibility to existing Picoclaw behavior | - Pending |
| Self-hosting teams are primary operator | Best fit for OSS adoption and early deployment motion | - Pending |

---
*Last updated: 2026-02-23 after initialization*
