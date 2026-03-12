# Session runtime and Daytona adapter design

## Purpose

Define how Minerva should preserve pi coding agent semantics while substituting hosted session persistence and Daytona-backed execution.

## References

- [`services/orchestrator/src/runtime/run-execution.service.ts`](../../../services/orchestrator/src/runtime/run-execution.service.ts)
- [`services/orchestrator/src/sandbox/workspace-manager.ts`](../../../services/orchestrator/src/sandbox/workspace-manager.ts)
- [`services/orchestrator/src/tools/index.ts`](../../../services/orchestrator/src/tools/index.ts)
- [`docs/specs/sandbox-execution.md`](../../specs/sandbox-execution.md)
- [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)

## Proposed runtime layers

### 1. Session runtime adapter

Introduce a Minerva-owned runtime abstraction that behaves like a hosted equivalent of pi's `AgentSession`.

Suggested responsibilities:

- load session state from Postgres
- reconstruct context from session entries
- resolve runtime resources for the active workspace
- create the pi-compatible tool surface for the current sandbox
- expose operations analogous to `prompt()`, `steer()`, `followUp()`, and resume
- subscribe to and normalize runtime events
- finalize durable records after each completed boundary

This adapter is the semantic compatibility layer. `RunExecutionService` should orchestrate runs around it instead of directly constructing a fresh agent from pack files each time.

### 2. Pi-core execution harness

Inside one run attempt, the runtime adapter can still use `pi-agent-core` for the actual loop, but it should inject:

- reconstructed message history
- active model and thinking configuration
- hosted tool implementations
- resource-derived prompt/context inputs
- a persistence callback path for finalized outputs

### 3. Daytona coding adapter

Keep Daytona as the execution substrate, but formalize a dedicated coding adapter that presents stable operations to the session runtime.

Suggested operations:

- `ensureSandbox(binding)`
- `ensureWorkspace(binding)`
- `exec(command, options)`
- `readFile(path, options)`
- `writeFile(path, content, options)`
- `listResources(path)`
- `disposeInactiveSandbox(binding)`

This prevents runtime semantics from leaking Daytona SDK details upward.

## Workspace and sandbox model

### Binding rules

Follow the already-approved hosted behavior:

- one Daytona sandbox per user-agent binding
- one workspace per user-agent binding inside that sandbox
- workspace path stable across resumed sessions for that binding
- sandbox disposal driven by inactivity policy

Suggested binding key:

`tenant_id + owner_id + agent_id`

A session references the binding, and each run resolves the currently active sandbox/workspace from that binding.

### Lifecycle states

Recommended sandbox lifecycle:

- `cold`: no active sandbox
- `provisioning`: sandbox being created or restored
- `warm`: sandbox active and reusable
- `expiring`: scheduled for idle cleanup
- `disposed`: binding exists but underlying sandbox was removed

Recommended workspace lifecycle:

- `missing`
- `materializing`
- `ready`
- `draining`

## Resource-loading behavior

Pi-style behavior depends on filesystem discovery. Minerva should preserve that experience by materializing a predictable runtime resource tree inside the workspace.

### Mounted resource set

The workspace should contain a controlled runtime root with at least:

- project `AGENTS.md`
- skills directory content
- prompt templates or prompt-command files if supported
- extension resources that are approved for v1
- runtime metadata files needed for compatibility shims

### Source of truth

Resources may originate from:

- stored agent pack assets
- repo checkout or synced project files
- Minerva-managed generated compatibility files

The runtime should not load these directly from the orchestrator host path at execution time.

### Precedence rules

Recommended precedence, highest first:

1. session/workspace-local overrides generated for the active binding
2. project or agent-pack resources for the selected agent
3. platform defaults bundled with Minerva

Precedence must be deterministic so resume behavior is stable.

### Materialization strategy

For v1, prefer an explicit workspace materialization step before agent execution:

1. resolve resource manifest for the active agent/session binding
2. compare with last applied manifest hash
3. write missing or changed files into the workspace runtime root
4. record the applied manifest version in Postgres and optionally in the workspace

This gives pi-like file discovery while keeping hosted control over what becomes visible inside Daytona.

## Tool adapter expectations

The built-in coding tools should preserve pi-facing semantics while routing to Daytona.

### `bash`

Must support:

- cancellation via run signal
- streaming stdout/stderr updates
- exit code reporting
- workspace-relative working directory behavior
- truncation/full-output metadata when output is large

### `read` and `write`

Must support:

- workspace-root scoping
- path traversal protection
- encoding/size limits
- deterministic error shapes suitable for replay and export

### Future tools

Even if v1 only exposes the current coding tools, the adapter boundary should leave room for:

- edit/patch-style tools
- search/listing tools
- extension-registered tools

## Failure handling expectations

The runtime adapter should translate infrastructure failures into stable runtime errors.

Examples:

- sandbox provisioning timeout
- workspace materialization failure
- resource manifest mismatch
- sandbox missing during resume
- path validation errors
- tool cancellation vs hard execution failure

Each error should map to:

- a user-safe SSE payload
- a durable run error record
- a machine-readable error code for later retries or support tooling

## Minimal refactor direction from current code

Current `RunExecutionService` mixes:

- queue control
- workspace acquisition
- resource loading
- prompt assembly
- direct `Agent` construction
- event forwarding
- terminal run finalization

Layer 2 planning should split this into:

- session command service
- session runtime adapter
- session repository
- sandbox binding manager
- resource materializer
- event recorder / SSE broadcaster

## Deferred items

- workspace snapshot/restore
- public branch navigation APIs
- non-HTTP developer SDK surface
- unrestricted extension loading

## Layer 2 planning outputs needed

- adapter interfaces with exact method signatures
- sandbox binding schema and idle-disposal policy
- resource manifest format and hashing rules
- runtime error taxonomy
- sequence diagrams for prompt, resume, cancel, and timeout flows
