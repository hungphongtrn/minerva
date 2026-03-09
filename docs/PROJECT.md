# Project: Minerva

Minerva is a self-hosted OSS runtime for running "agent packs" in a controlled sandbox, with real-time streaming suitable for building UIs.

The near-term focus is the **orchestrator layer** (TypeScript/NestJS), which wraps `@mariozechner/pi-agent-core` and uses the Daytona TS SDK to execute agent tool calls inside sandboxes.

## What We Are Building (v0)

### Core promise

- Users can run an agent that streams progress via SSE.
- Any code execution and filesystem access happens inside a Daytona sandbox.
- Skills exist as guidance text only in v0; they do not add new executable capabilities.

### Phase 1 focus: Developers BYO Infra

In the first phase, Minerva targets **developers/operators** who want to self-host agent deployments by bringing their own infrastructure (BYO infra), such as:

- Compute/sandbox provider: Daytona (self-hosted or managed)
- Metadata store: Postgres (self-hosted or managed)
- Object storage (future snapshots/exports): S3/MinIO

The goal is to provide the OSS runtime layer that can be deployed into an existing stack, before building higher-level tooling for business users.

### Agent packs

Agent packs are simple and business-friendly:

```
AGENTS.md                 # identity / stance / rules
.agents/skills/**/SKILL.md # instructional guidelines
```

### Execution model

- Orchestrator accepts a user message, runs the agent loop, and streams events via SSE.
- NestJS is the standard backend framework for long-lived Minerva services so modules, controllers, dependency injection, and testing patterns stay consistent across services.
- Tool execution is limited to a minimal set and runs in the sandbox.
- Per-user serialization (queue/lease) prevents concurrent mutations for the same user.

### v0 tool surface (minimal)

- `read`  : read file contents (sandbox)
- `write` : write file contents (sandbox)
- `bash`  : execute commands and stream stdout/stderr (sandbox)

## What We Are NOT Building Yet

- External authenticated tool ecosystem (MCP/connectors/tool gateways)
- Workspace persistence (snapshot/restore, exports/download links, retention/GC)
- Rich agent memory systems
- Marketplace/platform for creating multiple OSS runtimes

## Key Constraints / Invariants

- Sandbox-only execution: no host execution for user-directed tooling.
- No long-lived secrets in the sandbox.
- No general outbound network from the sandbox (policy-driven; v0 assumes "no").
- SSE event stream is a first-class API contract.

## Primary Users

- Phase 1: developers/operators who self-host the runtime and bring their own infrastructure.
- Later: business team members who want to distill an existing process into an agent pack.

## Success Criteria (v0)

- A user can run an agent and see streaming output + tool progress via SSE.
- Tool calls map reliably to Daytona sandbox operations.
- Runs are safely serialized per user and are cancellable.
- The system is understandable and extensible (adding tools later does not require rewriting eventing).

## References

- Architecture notes: `docs/architecture/agent-runtime-v0.md`
- Backend service framework guidance: `docs/architecture/backend-service-framework.md`
- pi-agent-core reference: `docs/research/pi-agent-core/README.md`
