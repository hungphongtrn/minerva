# Phase 2: Workspace Lifecycle and Agent Pack Portability - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver durable per-user workspace continuity and a template-scaffold-to-registered-agent-pack flow that runs with equivalent user-facing semantics across local Docker Compose and BYOC profiles, including sandbox routing/lifecycle controls (reuse healthy active sandbox, hydrate/create when needed, exclude unhealthy sandboxes, and idle auto-stop).

</domain>

<decisions>
## Implementation Decisions

### Workspace continuity rules
- Use one durable workspace per user for v1.
- Prioritize immediate readiness: create workspace automatically on first eligible use, then reuse it across sessions.
- Product intent is fast spin-up of an agent application (via agent pack) that is immediately usable in multi-tenant/scalable operation.

### Template-to-pack flow
- Follow Picoclaw conventions for scaffold and registration semantics.
- Registration binds to a path-linked pack (folder remains the source of truth).
- Validation failures block registration and return a clear checklist of missing/invalid items.
- Pack updates are auto-detected from source changes (no mandatory republish step for routine edits).

### Portability profile behavior
- Equivalent semantics means same user-facing behavior, while infrastructure internals may differ.
- Operate local-first: keep as many services locally available as possible.
- Switching to cloud options should primarily be environment-argument changes, not workflow changes.
- Daytona Cloud is the prioritized BYOC path for v1.
- Daytona self-host is explicitly supported as a practical option.

### Sandbox lifecycle behavior
- Always reuse an already active healthy sandbox for a workspace.
- Exclude unhealthy sandboxes immediately from routing and replace them.
- Idle auto-stop uses a single platform default TTL for this phase.
- Same-workspace concurrent write handling should align with Picoclaw agent behavior in this phase (no extra user-level concurrency semantics introduced here).

### OpenCode's Discretion
- Missing/corrupted workspace handling policy details (user delegated).
- Exact continuity persistence depth for environment artifacts vs rebuilt runtime details (user delegated).
- Profile capability mismatch behavior and remediation policy details (user delegated).

</decisions>

<specifics>
## Specific Ideas

- "The dev team can quickly spin up an Agent application (via agent pack) and it will be ready immediately for multi-tenant and scalable."
- "Follow picoclaw" for scaffold/registration semantics.
- Prioritize Daytona Cloud, with Daytona self-host as a handy option.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 02-workspace-lifecycle-and-agent-pack-portability*
*Context gathered: 2026-02-23*
