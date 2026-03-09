## Why

Minerva needs a self-hostable, developer-friendly runtime that can execute autonomous agents safely and predictably against a sandboxed workspace while streaming progress to UIs in real time. Today we have the conceptual model and dependencies (pi-agent-core, Daytona, Postgres/MinIO), but no concrete orchestrator layer that ties them together with clear isolation and event streaming.

This change establishes the v0 OSS infrastructure layer for BYO-infra agent deployment: an orchestrator that wraps `@mariozechner/pi-agent-core` and delegates all execution to Daytona sandboxes.

## What Changes

- Add a TypeScript orchestrator service that runs the agent loop and exposes a server-side SSE stream for UI rendering.
- Define and implement the minimal executable tool surface for v0: `read`, `write`, `bash`.
- Ensure all tool execution and filesystem access happen inside a Daytona sandbox (no host execution).
- Add per-user run serialization (queue/lease) and cancellation/timeouts.
- Load agent packs (`AGENTS.md` + `.agents/skills/**/SKILL.md`) as instructional context; skills are textual-only in v0 and do not add new executable capabilities.
- Document the event contract and mapping from pi-agent-core events to SSE.

## Capabilities

### New Capabilities

- `agent-packs`: Define the minimal agent pack format (AGENTS.md + skills) and how packs are loaded into an agent run.
- `run-orchestration`: Define run lifecycle, per-user serialization, cancellation, and core run metadata.
- `sandbox-execution`: Define how `read`/`write`/`bash` execute inside Daytona, including streaming stdout/stderr and enforcing sandbox-only execution.
- `event-streaming`: Define the SSE event contract for UI rendering and how it maps to pi-agent-core and tool execution events.

### Modified Capabilities

- (none)

## Impact

- Introduces a new TypeScript service entrypoint and runtime dependencies (Node.js >= 20).
- Defines the initial public API surface for running agents (SSE stream + run endpoints).
- Establishes the execution boundary and safety posture (sandbox-only execution; no long-lived secrets and no general outbound network from sandbox in v0).
- Creates baseline specs that future work (snapshots, external tools/connectors, multi-tenancy) will build on.
