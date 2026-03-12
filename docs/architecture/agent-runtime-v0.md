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

Reference: `docs/research/pi-agent-core/INDEX.md` and `docs/research/pi-agent-core/events.md`.

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

## Model Provider Integration

The orchestrator uses a configurable model provider system to connect to real LLM backends:

### Supported Providers

- **OpenAI**: GPT-4, GPT-3.5-turbo, and other OpenAI models
- **Anthropic**: Claude 3 Opus, Sonnet, Haiku, and other Anthropic models

### Configuration

Provider selection is configured via environment variables:

```bash
MODEL_PROVIDER=openai  # or 'anthropic'
OPENAI_API_KEY=sk-...  # required if MODEL_PROVIDER=openai
ANTHROPIC_API_KEY=sk-ant-...  # required if MODEL_PROVIDER=anthropic
```

Optional parameters:
- `MODEL_NAME`: Override default model selection
- `MODEL_TEMPERATURE`: Control randomness (0-2)
- `MODEL_MAX_TOKENS`: Limit response length

### Architecture

The model provider system consists of three layers:

1. **Configuration Layer** (`ModelProviderConfig`): Validates environment variables using Zod schemas, provides fail-fast error messages for missing/invalid config

2. **Service Layer** (`ModelProviderService`): Factory for creating StreamFn instances compatible with pi-agent-core, implements health checks, handles provider-specific logic

3. **Integration Layer** (`RunExecutionService`): Injects the provider service, verifies health before starting runs, translates provider errors to user-friendly messages

### Health Checking

The `/health` endpoint validates provider connectivity:
- Returns HTTP 200 when provider is configured and accessible
- Returns HTTP 503 with descriptive error when provider is unavailable
- Checks API key format and basic configuration validity

### Error Handling

Provider errors are automatically enhanced with descriptive messages:
- Rate limit errors include retry guidance
- Authentication errors prompt checking API keys
- Timeout errors suggest checking network or reducing request size
- Quota errors indicate billing issues

See `docs/setups/model-provider-setup.md` for detailed setup instructions and `docs/setups/model-provider-troubleshooting.md` for common issues.

## Deferred Topics (Explicitly Parked)

- External authenticated tools (MCP/connectors/tool gateways)
- Capability profiles/toolpacks to reconcile "skills" with finite sandbox environments
- Rich memory systems attached to the agent (scoping, isolation, retention)
- Workspace persistence: snapshot/restore, downloads/exports, retention, garbage collection
- Multi-model routing or provider fallback
- Fine-grained model parameter tuning beyond basic configuration

## Known Gaps / Risks (Non-exhaustive)

- Prompt injection can still cause destructive local actions via `bash`; sandbox-level resource and safety policies are still required.
- Without workspace persistence, users cannot reliably "resume" a prior filesystem state; v0 should set expectations accordingly.
- Per-user single workspace is simple but may block multi-project workflows; keep the model extensible.
- Real LLM providers introduce latency and costs compared to scripted runtime; UI expectations should be set accordingly.
- Provider rate limits and quotas can interrupt service availability; monitoring and alerting should be implemented.
