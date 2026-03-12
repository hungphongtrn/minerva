# pi coding agent SDK research note

## Purpose and scope

This note summarizes the `@mariozechner/pi-coding-agent` SDK based primarily on `packages/coding-agent/docs/sdk.md` in `pi-mono`. It focuses on behavior and integration facts relevant to a Minerva design discussion, especially where Minerva wants Postgres-backed persistence and Daytona sandbox execution instead of direct local shell access.

## What the SDK is

The SDK is a higher-level package on top of `@mariozechner/pi-agent-core`. It wraps the core agent loop with:
- session creation and restoration
- model/auth/settings management
- resource discovery for extensions, skills, prompt templates, and `AGENTS.md`
- built-in coding tools and run modes
- a richer session/tree abstraction for branching and navigation

The main entry point is `createAgentSession()`, which returns an `AgentSession` plus extension loading results and an optional model fallback warning.

## Key SDK concepts

### 1. `createAgentSession()` is the composition root
It wires together model selection, settings, tools, resource loading, persistence, and extensions. If no `ResourceLoader` is supplied, it uses `DefaultResourceLoader`.

### 2. `AgentSession` is the main runtime handle
Important capabilities:
- `prompt()` to send a message and wait for completion
- `steer()` to interrupt ongoing work after the current tool finishes
- `followUp()` to enqueue work after the current agent run completes
- `subscribe()` for event streaming
- session lifecycle operations like `newSession()`, `switchSession()`, `fork()`, and `navigateTree()`
- model/thinking controls like `setModel()`, `cycleModel()`, `setThinkingLevel()`
- compaction, abort, and disposal

This makes the SDK more than a stateless request API; it is a stateful long-lived runtime object.

### 3. Resource loading is a first-class behavior source
`DefaultResourceLoader` discovers and merges:
- extensions
- skills
- prompt templates / slash commands
- themes
- `AGENTS.md` context files
- settings, models, auth, sessions via standard directories

This means behavior is partly defined by files on disk, not only by programmatic configuration.

## Session and persistence behavior

### Session model
The SDK supports:
- in-memory sessions with no persistence
- persistent sessions stored via `SessionManager`
- continuing the most recent session for a working directory
- opening a specific saved session file

### Persistence shape
The doc points to session files as JSONL and exposes `sessionFile`. Sessions are tree-structured, using `id` and `parentId` links rather than a strictly linear transcript.

Supported tree operations include:
- get full tree or path to current leaf
- branch to an earlier entry
- branch with summary
- create a branched session in a new file
- label checkpoints
- fork from a specific entry
- in-place navigation to another branch (`navigateTree()`)

### Durability boundaries
Settings writes are explicitly asynchronous; callers must `flush()` for a durability boundary. That is a useful signal for Minerva: the reference implementation is comfortable with buffered persistence instead of synchronous writes on every mutation.

### Implication for Minerva
This session model looks portable, but the backing store should change:
- pi reference: local file-oriented session persistence, JSONL session files, path-based discovery
- Minerva target: Postgres-backed session/event/message persistence with explicit query APIs

A Minerva adaptation likely needs to preserve the tree semantics and IDs while replacing file-based persistence and “continue recent in cwd” discovery with database queries scoped by workspace/project/run.

## Tool and command execution model

### Built-in tools
The SDK ships built-in coding tools and read-only tools. Examples include:
- read
- bash
- edit
- write
- grep
- find
- ls

If no explicit tools are passed, the SDK creates tools using the configured `cwd`. If callers pass an explicit `tools` array with a custom `cwd`, they must use tool factory helpers so path resolution uses that `cwd` instead of `process.cwd()`.

### Custom tools
Custom tools are defined with schema-validated parameters and an async `execute()` function. They are provided either:
- directly via `customTools`
- indirectly via extensions calling `pi.registerTool()`

The tool interface supports streaming updates (`onUpdate`) and cancellation (`signal`), which matters for long-running operations and UI streaming.

### Prompt templates vs extension commands
The SDK distinguishes two command-like behaviors:
- file-based prompt templates: expanded into text before sending/queueing
- extension commands (for example slash commands implemented by extensions): executed immediately, even during streaming, and they manage their own LLM interaction

Queued messages (`steer()`/`followUp()`) can expand file-based templates but reject extension commands.

### Implication for Minerva
This is one of the biggest adaptation areas:
- replicable concept: schema-based tools, streaming tool updates, cancellation, explicit queueing rules
- needs adaptation: `bash`/filesystem tools should target Daytona sandboxes, not the Minerva host or arbitrary bare-metal `cwd`

Minerva should treat tool execution context as a sandbox/workspace handle, not as local process state.

## Event and streaming model

The session exposes a subscription API with fine-grained events, including:
- `agent_start` / `agent_end`
- `turn_start` / `turn_end`
- `message_start` / `message_end`
- `message_update` for assistant deltas
- `tool_execution_start` / `tool_execution_update` / `tool_execution_end`
- `auto_compaction_start` / `auto_compaction_end`
- `auto_retry_start` / `auto_retry_end`

`message_update` carries assistant-level delta events such as text deltas and thinking deltas.

Important behavioral implications:
- the API is event-first, not polling-first
- tool output streams independently from assistant text
- turn boundaries are explicit, which is useful for run orchestration and replay
- agent end events expose the new messages generated by the run

### Implication for Minerva
This model maps well onto SSE/WebSocket streaming and append-only event persistence in Postgres. It should be feasible to preserve the event taxonomy closely, though Minerva may want stronger run IDs, sandbox IDs, and persistence metadata on each event.

## Extensibility hooks

The SDK is highly extensible through the `ResourceLoader` and extension system.

Hooks and override points called out in the doc include:
- `systemPromptOverride`
- `skillsOverride`
- `agentsFilesOverride`
- `promptsOverride`
- additional extension paths
- inline `extensionFactories`
- shared extension event bus via `createEventBus()`

Extensions can:
- register tools
- subscribe to agent/session events
- add commands
- communicate through an event bus

This is a strong sign that pi expects runtime composition rather than a fixed closed runtime.

## Replicable exactly vs likely needing adaptation for Minerva

### Appears replicable nearly exactly
- `AgentSession` as the top-level stateful runtime abstraction
- event subscription model and major event categories
- queueing semantics for `prompt()`, `steer()`, and `followUp()`
- session tree semantics (`id`/`parentId`, branching, labels, fork/navigation)
- schema-defined tools with streaming updates and cancellation
- extension/resource-loader concept for loading behavior from project/global context
- settings layering concept: global + project overrides

### Likely needs adaptation
- file-backed session persistence -> Postgres tables and queries
- filesystem-based resource discovery -> workspace-aware loaders, likely backed by repo checkout metadata and/or DB config
- `cwd`-centric local tool execution -> Daytona sandbox execution context
- built-in shell/file tools -> sandbox RPC or sandbox service adapters
- local auth/settings/models JSON files -> Minerva-managed secrets/config abstractions
- “continue most recent session in cwd” -> continue by project/workspace/user/run context
- run modes like TUI/RPC -> Minerva service endpoints and frontend streaming contracts

## Minerva-specific adaptation context

For Minerva, the most relevant translation is:
- persistence should move from local files and JSONL session logs to Postgres-backed sessions, messages, tree edges, labels, and event records
- command/file tools should execute in Daytona sandboxes, not on the orchestrator host
- any path-derived behavior should become workspace/sandbox-derived behavior
- extension and prompt-loading should remain possible, but likely through controlled workspace mounts or service-managed registries rather than unrestricted host discovery

## Open questions / unknowns

1. The SDK doc names session files and tree APIs but does not specify the exact JSONL record schema, concurrency behavior, or recovery guarantees.
2. It is not clear from this doc alone whether session persistence is append-only for all mutations or partly rewrite-based.
3. The compaction algorithm is exposed operationally, but the exact compaction data model and restore semantics are not described here.
4. Retry behavior is surfaced via events/settings, but exact retry triggers and idempotency expectations need source review.
5. Extension command execution is described at a high level, but the contract between commands and the session timeline is not fully specified in this doc.
6. Security boundaries for built-in tools are assumed to be local-process boundaries; Minerva needs a stricter sandbox/service trust model.

## Bottom line

The pi coding agent SDK is best understood as a stateful agent runtime that combines `pi-agent-core` with file-oriented session management, tooling, and resource discovery for coding workflows. Its event model, queueing semantics, branching session tree, and extension architecture look directly useful for Minerva. The largest changes required are infrastructure substitutions: Postgres instead of local JSONL/file persistence, and Daytona sandbox execution instead of direct local shell/filesystem tools.
