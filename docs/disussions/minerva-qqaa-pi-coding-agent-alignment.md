# minerva-qqaa discussion conclusion: pi coding agent alignment

## Scope

This document captures the design discussion conclusions for `minerva-qqaa`, which aims to align Minerva with the pi coding agent SDK behavior while adapting infrastructure for a deployed multi-tenant environment.

## Related references

- Bean: [`minerva-qqaa`](../../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)
- Project direction: [`docs/PROJECT.md`](../PROJECT.md)
- Research: [`docs/research/pi-coding-agent-sdk.md`](../research/pi-coding-agent-sdk.md)
- Decisions log: [`docs/DECISIONS.md`](../DECISIONS.md)

## Confirmed conclusions

### 1. Fidelity target

Minerva should target near-exact pi coding agent SDK semantics rather than using only `pi-agent-core` directly.

The desired approach is:
- preserve pi coding agent session/runtime behavior as closely as practical
- adapt persistence to Postgres
- adapt command and file execution to Daytona sandboxes

### 2. Session model

For v1:
- branching is not exposed to users
- branch-capable internals should still be preserved so the runtime can evolve toward pi compatibility later
- behavioral compatibility matters more than internal implementation matching
- export compatibility should be pursued where practical

### 3. Persistence model

Minerva should use a hybrid Postgres persistence model that follows pi coding agent behavior closely.

The intended direction is:
- durable session/message/event records in Postgres
- query-friendly relational projections where useful
- behaviorally compatible export shape when possible

From source-level research on pi coding agent session persistence:
- pi does not persist every streaming delta
- pi persists durable records when messages end
- pi keeps live streaming updates separate from durable session history
- normal persistence is append-oriented, with compaction represented as appended records rather than destructive rewrites

Therefore Minerva should mirror that behavior:
- live SSE streaming for runtime deltas and tool progress
- durable persistence for finalized records only

### 4. Sandbox and workspace model

The execution environment should be:
- one Daytona sandbox per user-agent
- one workspace per user-agent
- workspace rooted as a folder inside the sandbox
- sandbox disposed on inactivity

All coding tools must execute inside the sandbox.

### 5. Tooling surface

Minerva should keep the built-in coding tool behavior aligned with pi coding agent.

Important constraint:
- tool execution must happen inside Daytona, not on the Minerva host

### 6. Resource loading model

The sandbox filesystem should contain the resources the runtime expects, including:
- `AGENTS.md`
- skills
- related prompt/runtime files needed for SDK-style filesystem loading

This allows the runtime to operate with a normal filesystem-based behavior model even though Minerva is deployed remotely.

### 7. Slash/prompt command behavior

The runtime may retain slash/prompt command support for development speed and compatibility.

For v1 product behavior:
- consumer-facing APIs and UI should block slash commands
- internal or developer-oriented flows may still keep the capability available later if needed

### 8. Resume behavior

Resume semantics should match pi coding agent behavior as closely as practical.

For v1:
- restore conversation state
- restore workspace binding
- restore sandbox binding
- do not require workspace checkpointing

Current constraint:
- newly spawned sandboxes start from predefined structure only
- workspace checkpoint/restore is deferred

### 9. Product and tenancy direction

Minerva targets a multi-tenant setting.

There are two important user roles:
- developers: create/configure agents and may build their own UIs
- consumers: use the created agents

Phase 1 emphasis:
- prioritize actual software developers who want to quickly build agents for consumers
- provide Minerva HTTP/SSE APIs and a UI for consumers
- keep developer integrations flexible so custom UIs can be built on top

### 10. Trust model

Trust restrictions should remain flexible for now.

For the current phase:
- allow code execution inside the sandbox
- defer tighter policy restrictions and hardening to a later phase

### 11. Deferred items

These are explicitly deferred from v1 scope:
- exposed branching UX
- compaction and summarization as product features
- workspace checkpointing and restore
- non-HTTP developer SDK surface

## Practical interpretation for Minerva

The emerging architecture is not a thin wrapper around `pi-agent-core`.

Instead, Minerva should act like a hosted pi coding agent runtime with infrastructure substitutions:
- pi local/session JSONL persistence -> Minerva Postgres persistence plus export adapter
- pi local shell/filesystem execution -> Daytona sandbox execution
- pi local runtime UX -> Minerva HTTP/SSE APIs and UI

## Remaining pre-planning questions

The major product decisions are largely resolved. What remains before implementation planning is mainly technical design work:
- exact Postgres schema and export adapter shape
- exact sandbox lifecycle management and inactivity disposal rules
- exact API and SSE contracts for consumer and developer use
- exact mapping between pi durable records and Minerva persistence tables
