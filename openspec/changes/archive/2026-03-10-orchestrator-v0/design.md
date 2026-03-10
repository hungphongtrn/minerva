## Context

Minerva is an OSS, self-hostable runtime for running "agent packs" with strong execution isolation and real-time UI streaming. In phase 1, we target developers/operators doing BYO-infra agent deployments.

The current repo includes research notes for `@mariozechner/pi-agent-core` (agent loop + event streaming) and is aligned on using Daytona as the sandbox substrate. v0 intentionally defers workspace snapshot/restore and external authenticated tools/connectors.

Key constraints for v0:

- All code execution and filesystem interaction MUST occur inside a Daytona sandbox.
- The sandbox has no general outbound network in v0.
- No long-lived secrets exist in the sandbox.
- The orchestrator MUST stream progress suitable for UI rendering via SSE.

## Goals / Non-Goals

**Goals:**

- Build a TypeScript orchestrator service that wraps `@mariozechner/pi-agent-core`.
- Provide an SSE event stream for each run with low-latency updates.
- Implement the minimal tool surface (`read`, `write`, `bash`) with sandbox-only execution via Daytona.
- Enforce per-user serialization (queue/lease) and support cancellation/timeouts.
- Load agent packs (`AGENTS.md` + `.agents/skills/**/SKILL.md`) as instructional context (skills are textual-only in v0).

**Non-Goals:**

- External authenticated tool ecosystem (MCP/connectors/tool gateways).
- Workspace persistence (snapshot/restore, exports/download links, retention/GC).
- Rich long-term memory systems beyond pi-agent-core message history.
- Marketplace/platform features.

## Decisions

### Use TypeScript end-to-end for v0 runtime

**Decision:** Implement the orchestrator, APIs, and sandbox adapter in TypeScript (Node.js >= 20).

**Rationale:** Both `@mariozechner/pi-agent-core` and the Daytona TS SDK are TypeScript-first, simplifying integration and allowing direct event forwarding.

**Alternatives considered:** Python (FastAPI) orchestrator.
**Why not:** Would require building/maintaining a second agent-loop integration layer or bridging via IPC.

### Treat pi-agent-core events as the canonical internal event stream

**Decision:** Model run streaming as a thin adaptation of pi-agent-core events, adding a small number of orchestrator-level lifecycle events.

**Rationale:** pi-agent-core already provides a fine-grained event model (`message_update`, `tool_execution_*`) suited for SSE and UI rendering.

**Alternatives considered:** Define a custom event model and map pi-agent-core into it.
**Why not:** Higher complexity and risk of losing useful streaming detail.

### Tool boundary is the extensibility seam (even in v0)

**Decision:** Implement `read`/`write`/`bash` as pi-agent-core tools whose `execute()` methods delegate to a Daytona adapter.

**Rationale:** Future capabilities (connectors, policies, profiles) should be introduced by adding new tools and policies without rewriting the run loop or SSE stream.

### Sandbox is authoritative for execution; orchestrator is authoritative for scheduling

**Decision:** All execution and filesystem operations happen in a Daytona workspace; the orchestrator manages run lifecycle, queuing, cancellation, and streaming.

**Rationale:** Keeps the trust boundary clear and allows independent scaling of orchestrator workers and sandbox capacity.

### Workspace model: ephemeral scratch per run

**Decision:** In v0, the sandbox filesystem is treated as scratch space. The orchestrator may reuse a warm sandbox for performance, but does not implement snapshot/restore.

**Rationale:** Defers the hard problems (exports, retention, incremental snapshots) until the tool ecosystem and persistence requirements are clearer.

### Per-user serialization via queue/lease

**Decision:** Runs are serialized per `user_id` (one active run per user at a time).

**Rationale:** Simplifies filesystem consistency and reduces concurrency hazards for v0.

**Alternatives considered:** Per-session or per-workspace concurrency.
**Why not (for v0):** Requires additional workspace identity model and conflict resolution.

## Risks / Trade-offs

- **[Limited skill power]** Skills are instructional-only, which may create an expectation gap for business authors. → Mitigation: clear UX messaging and a roadmap for external tools/profiles.
- **[bash is dangerous]** Prompt injection can cause destructive local actions via `bash` even in a sandbox. → Mitigation: sandbox resource limits, timeouts, restricted network, and later command policies.
- **[Warm sandbox reuse]** Reusing sandboxes can leak state across runs for the same user and complicate debugging. → Mitigation: v0 defaults to clean workspace per run (or explicit per-user warm reuse), with clear cleanup rules.
- **[Ordering + backpressure]** SSE requires consistent ordering; tool logs may be large. → Mitigation: event IDs, bounded buffering, and backpressure strategy (documented).

## Migration Plan

- Ship as a new TS service with a small API surface (start run, SSE stream, cancel run).
- No data migrations required in v0; persistence can start in-memory and move to Postgres behind interfaces.
- Rollback: disable the new service; no persistent workspace state to recover.

## Open Questions

- What is the minimal persistent store needed for multi-instance deployments (leases, run state, SSE replay)?
- How to enforce "no outbound network" in Daytona across self-hosted and managed configurations?
- What is the long-term workspace identity model (keep `user_id` only vs add `workspace_id` and `tenant_id`)?
- What should the stable SSE event schema/versioning look like for external UI consumers?
