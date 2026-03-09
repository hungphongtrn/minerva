# Agent Runtime v0 (Explore Notes)

These notes capture an explore-mode discussion about a self-hosted OSS agent runtime focused on an orchestrator + sandbox execution.

## Goals

- Let business users create an "agent pack" quickly by providing:
  - `AGENTS.md` (agent identity / operating stance)
  - `.agents/skills/**/SKILL.md` (instructions/guidelines)
- Orchestrate agent execution while enforcing that code execution + filesystem access happens inside a sandbox.
- Stream fine-grained progress to a UI via SSE.

## Non-goals (for v0)

- No external authenticated tool ecosystem yet (MCP/connectors deferred).
- Skills are "textual guidance" only; they do not add executable capabilities.

## Agent Pack Baseline

Baseline structure:

```
agent-pack/
  AGENTS.md
  .agents/
    skills/
      brainstorming/SKILL.md
      planning/SKILL.md
      coding/SKILL.md
      debugging/SKILL.md
      testing/SKILL.md
      documentation/SKILL.md
```

## Core Constraints / Invariants

- **All code execution happens in the sandbox** (Daytona workspace).
- **No long-lived secrets exist in the sandbox** (no API keys, bearer tokens, etc.).
- **No general outbound network from the sandbox** (at most a narrow runtime-controlled channel if needed).
- **SSE is required** so UIs can render: model streaming + tool execution progress.

## Components

- **API/Auth**: a NestJS service edge that accepts user requests and establishes an SSE stream.
- **Run Orchestrator**: queues work, enforces per-user serialization, maintains run state, fans out SSE.
- **Agent Worker(s)**: wraps `@mariozechner/pi-agent-core` to run the agent loop and emit events.
- **Sandbox Fleet**: Daytona workspaces (per user/workspace) that actually run tools.
- **Metadata Store**: Postgres for runs, steps, leases (implementation detail).

Reference: `docs/research/pi-agent-core/README.md` and `docs/research/pi-agent-core/events.md`.

## v0 Tooling Model (Minimal)

Only three tools exist, all executed in the sandbox:

- `read`: read file contents
- `write`: write file contents
- `bash`: run a command and stream stdout/stderr

Skills may instruct *when* to use these tools but cannot introduce new ones in v0.

## Multi-user Execution Model

- Runs for different users execute concurrently (scale agent workers horizontally).
- Runs for the same `user_id` are serialized via a queue/lease (one active mutation at a time).
- Current preference: one persistent workspace per `user_id`.
  - Note: this is simple but can become limiting for multi-project usage; a future extension is `(tenant_id, user_id, workspace_id)`.

## Workspace Lifecycle (Ephemeral per Run)

High-level idea:

- In v0, the sandbox filesystem is treated as **scratch space** for a single run.
- The orchestrator may keep a sandbox warm for performance, but **does not** implement workspace snapshot/restore.
- Persisted state is limited to run artifacts needed for UX/operations (event stream, final messages, basic run metadata).

## Agent <-> Sandbox Interaction (Event-Driven)

Wrap `pi-agent-core` so its tool execution hooks call Daytona.

The NestJS orchestrator should map pi-agent-core events to SSE nearly 1:1:

- `agent_start` / `agent_end`
- `turn_start` / `turn_end`
- `message_start` / `message_update` / `message_end`
- `tool_execution_start` / `tool_execution_update` / `tool_execution_end`

This gives a stable UI contract even as tools evolve later.

## EV Assistant Example (State Diagram)

EV assistant is used as a representative example. In v0 (no external tools), the agent may only guide users and manipulate local workspace via `read/write/bash`.

Single run state machine:

```
RECEIVED
  -> QUEUED (per user_id)
  -> LEASED
  -> ENSURE_SANDBOX (Daytona workspace)
  -> AGENT_LOOP
      - LLM streaming
      - tool calls: read/write/bash executed in sandbox
  -> FINALIZE_RUN
  -> RELEASE_LEASE
  -> IDLE
```

Tool execution sub-flow (example: `bash`):

```
tool_execution_start
  -> daytona.exec(command)
  -> stream stdout/stderr as tool_execution_update
  -> tool_execution_end (exit code + structured result)
```

## Deferred Topics (Explicitly Parked)

- External authenticated tools (MCP/connectors/tool gateways)
- Capability profiles/toolpacks to reconcile "skills" with finite sandbox environments
- Rich memory systems attached to the agent (scoping, isolation, retention)
- Workspace persistence: snapshot/restore, downloads/exports, retention, garbage collection

## Known Gaps / Risks (Non-exhaustive)

- Prompt injection can still cause destructive local actions via `bash`; sandbox-level resource and safety policies are still required.
- Without workspace persistence, users cannot reliably "resume" a prior filesystem state; v0 should set expectations accordingly.
- Per-user single workspace is simple but may block multi-project workflows; keep the model extensible.
