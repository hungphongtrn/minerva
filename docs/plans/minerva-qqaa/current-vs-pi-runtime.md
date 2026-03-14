# Current orchestrator flow vs pi coding agent runtime proposal

## Purpose

Compare the current Minerva orchestrator implementation to the pi coding agent SDK behavior so later planning can focus on the real adaptation gaps instead of re-deciding product direction. This is proposal material, not ratified canonical architecture.

## References

- [`services/orchestrator/src/runtime/run-execution.service.ts`](../../../services/orchestrator/src/runtime/run-execution.service.ts)
- [`services/orchestrator/src/services/run-manager.ts`](../../../services/orchestrator/src/services/run-manager.ts)
- [`services/orchestrator/src/packs/loader.ts`](../../../services/orchestrator/src/packs/loader.ts)
- [`services/orchestrator/src/packs/assembler.ts`](../../../services/orchestrator/src/packs/assembler.ts)
- [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)
- [`docs/research/pi-agent-core/sessions.md`](../../research/pi-agent-core/sessions.md)

## Current Minerva flow

Today the orchestrator behaves like a single-run wrapper around `pi-agent-core`:

1. create a run record in the in-memory `RunManager`
2. queue work per owner lane
3. acquire a lease for the next run
4. create or reuse a Daytona workspace through `ISandboxAdapter`
5. load `AGENTS.md` and `.agents/skills/**/SKILL.md` from a server-side pack path
6. flatten pack identity + skills into one assembled system prompt
7. construct a fresh `pi-agent-core` `Agent`
8. subscribe to emitted agent events and forward them to SSE
9. execute built-in tools through the Daytona adapter
10. persist only final run metadata and final messages in memory

## Pi coding agent target behavior

The pi coding agent SDK behaves like a long-lived, stateful session runtime:

- `createAgentSession()` is a composition root for persistence, tools, settings, models, extensions, and resource loading
- session history is durable and tree-shaped, not just a per-run message array
- prompting, steering, follow-up, resume, branching, labels, and compaction all operate against one session object
- resource loading is filesystem-based and part of runtime semantics, not just prompt preprocessing
- persistence and eventing are separated: streaming deltas are transient while durable records are appended at message/session boundaries

## Main gap categories

### 1. Run-centric orchestration vs session-centric runtime

Current Minerva creates a new agent instance for each run and discards runtime state after completion.

Pi expects:

- durable session identity beyond a single run
- resume into an existing session context
- tree navigation and branch-capable internals
- runtime operations such as `prompt()`, `steer()`, `followUp()`, `fork()`, and navigation against the same session model

Design consequence:
Minerva needs a session runtime adapter that sits above raw run orchestration. Runs become execution attempts or turns within a durable session, not the primary state container.

### 2. In-memory run persistence vs durable session persistence

Current `RunManager` uses `InMemoryRunRepository`, stores terminal run metadata, and does not preserve tree entries, labels, or event-backed replay state.

Pi expects append-oriented durable session records.

Design consequence:
Move durable state to Postgres and split it into session records, session entries, run attempts, and streamed event projections.

### 3. Prompt assembly vs filesystem-backed resource loading

Current Minerva loads pack files on the orchestrator host and copies the resolved text into the system prompt.

Pi semantics depend on the runtime being able to discover:

- `AGENTS.md`
- skills
- prompt templates and slash commands
- extension resources
- session-related files

Design consequence:
Minerva should stop treating pack loading as only a build-time prompt assembly step. Resource loading should be modeled as a workspace-mounted runtime view with explicit precedence rules.

### 4. Minimal tool wrapping vs pi-compatible coding tool semantics

Current tool integration is close in spirit but still shallow:

- a simple tool registry wraps Daytona execution
- there is no hosted equivalent of a full `AgentSession`
- tool execution is attached to a run/workspace context, not a session runtime context

Design consequence:
Keep Daytona as the executor, but introduce a runtime adapter layer that presents pi-like semantics to the session while translating them into hosted sandbox operations.

### 5. SSE passthrough vs durable replay contract

Current SSE handling mostly forwards events during a live run and stores sequence state in process memory.

Pi-compatible hosted behavior needs:

- durable replay after disconnects and process restarts
- stable session/run identifiers on every event
- separation between transient deltas and durable finalized records
- compatibility between live streaming and exported session artifacts

## Comparison table

| Concern | Current Minerva | Pi-compatible target |
|---|---|---|
| Primary state object | Run | Session with branch-capable history |
| Persistence | In-memory run metadata | Postgres durable session + run + event records |
| Runtime lifetime | Fresh `Agent` per run | Long-lived logical session resumed across runs |
| Resource loading | Host-side pack parse + prompt assembly | Filesystem-style runtime resource discovery inside workspace view |
| Tool execution | Daytona adapter called from tools | Daytona-backed coding adapter under a session runtime |
| Resume | None beyond run lookup | Resume session state, workspace binding, sandbox binding |
| Branching internals | None | Preserve `id`/`parentId` entry graph internally |
| Export | Final messages only | Pi-shaped session artifact export |
| SSE replay | Live in-process stream behavior | Durable replay-safe event log |

## Layer 1 proposal baseline

The hosted architecture should be reframed as:

- hosted session service with pi-like behavior semantics
- run orchestration as execution control around that session service
- Postgres as the durable source of truth
- Daytona as the execution substrate
- workspace-mounted resources to preserve pi-like file discovery semantics

## Layer 2 questions

- which runtime methods are required for v1 compatibility and which are deferred behind internal-only APIs?
- should a single HTTP run map to one `prompt()` call or to a more explicit session command envelope?
- what minimal branch metadata must be stored now so future branching UX does not require data migration?
- which current SSE events remain public as-is and which need versioned wrappers?
