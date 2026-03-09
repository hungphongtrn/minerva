# Roadmap

This roadmap is scoped to building the OSS runtime (orchestrator + sandbox execution) first. Items are ordered roughly by dependency and value.

## Now: v0 Orchestrator + Sandbox MVP

- TypeScript service skeleton (API + SSE streaming)
- Integrate `@mariozechner/pi-agent-core` and forward its events to SSE
- Implement minimal tools (`read`, `write`, `bash`) as pi-agent-core tools
- Daytona TS SDK adapter:
  - workspace provisioning (create/reuse)
  - exec streaming (stdout/stderr)
  - file read/write primitives (either direct APIs or via exec)
- Per-user run serialization (queue + lease) and cancellation support
- Logging/tracing: correlate `run_id` across agent loop and sandbox execution
- Basic tests for: queue/lease, SSE event ordering, tool execution error handling
- Documentation:
  - keep `docs/architecture/agent-runtime-v0.md` aligned with implementation

## Next: v0.1 Hardening

- Resource limits/timeouts for sandbox tool execution
- Sandboxed "no network" enforcement validation (document how it is achieved in Daytona)
- Multi-run stability: retries, transient Daytona errors, cleanup
- Guardrails for `bash` (policy hooks; still sandbox-enforced)

## Later: Workspace Persistence

- Workspace identity model (`tenant_id`, `user_id`, optional `workspace_id`)
- Snapshot/export pipeline (object store) and restore semantics
- Retention + garbage collection policies
- Download links and audit trail for exports

## Later: External Tools and Auth

- Tool gateway / connectors (likely MCP-based)
- Credential model (tenant-scoped vs user-delegated), auditing, redaction
- Capability profiles/toolpacks to reconcile skills with finite sandbox environments

## Later: Multi-tenancy and Platform

- Strong tenant isolation model (authz, quotas, storage namespaces)
- Packaging/distribution of agent packs (signing, provenance, version pinning)
- Platform layer to help create/manage multiple OSS runtime deployments
