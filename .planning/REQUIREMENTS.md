# Requirements: Picoclaw Multi-Tenant OSS Runtime

**Defined:** 2026-02-23
**Core Value:** Any team can run Picoclaw safely for multiple users with strong isolation and predictable behavior, without building orchestration and sandbox infrastructure themselves.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Identity & Access

- [ ] **AUTH-01**: User can authenticate API requests with a personal API key.
- [ ] **AUTH-02**: User or operator can rotate and revoke an API key.
- [ ] **AUTH-03**: User can access only their own workspace resources.
- [ ] **AUTH-04**: User can send an idempotency key so retries do not create duplicate runs.
- [ ] **AUTH-05**: Operator can assign a basic role (owner/member) to control access behavior.
- [ ] **AUTH-06**: System assigns a random guest identity for requests without explicit user identity and marks that run as guest mode.

### Agent Bootstrap

- [ ] **AGNT-01**: User can create a new agent workspace from filesystem templates that include `AGENT.md`, `SOUL.md`, `IDENTITY.md`, and a `skills/` skeleton.
- [ ] **AGNT-02**: User can register an agent pack folder and run it without manual infrastructure wiring.
- [ ] **AGNT-03**: User can run the same agent pack in two deployment profiles: local Docker Compose and BYOC infrastructure (for example Postgres, queue, S3).

### Workspace & Isolation

- [ ] **WORK-01**: User has one persistent workspace shared across their sessions.
- [ ] **WORK-02**: User request is routed to an active healthy sandbox when available.
- [ ] **WORK-03**: User request can trigger sandbox creation and workspace attach when no active sandbox exists.
- [ ] **WORK-04**: System enforces a workspace lease lock so only one active writer operates on a user workspace at a time.
- [ ] **WORK-05**: System runs sandbox health checks before routing execution.
- [ ] **WORK-06**: System auto-stops idle sandboxes after configurable TTL.

### Execution & Scheduling

- [ ] **EXEC-01**: User requests for the same workspace are queued and processed in order.
- [ ] **EXEC-02**: Requests from different users can execute in parallel.
- [ ] **EXEC-03**: System retries transient failures with bounded backoff.
- [ ] **EXEC-04**: System moves failed jobs to dead-letter after retry exhaustion.
- [ ] **EXEC-05**: User or operator can cancel an active run.
- [ ] **EXEC-06**: System enforces per-user queue and concurrency caps to guarantee fairness.

### Event Streaming API

- [ ] **EVNT-01**: User can subscribe to run events via SSE.
- [ ] **EVNT-02**: Stream emits typed events (`message`, `tool_call`, `tool_result`, `ui_patch`, `state_update`, `error`).
- [ ] **EVNT-03**: Stream includes lifecycle events (`queued`, `running`, `cancelled`, `completed`, `failed`).
- [ ] **EVNT-04**: User can fetch final transcript and artifact snapshot after run completion.
- [ ] **EVNT-05**: User can subscribe to run events via WebSocket.
- [ ] **EVNT-06**: Event contract stays aligned with upstream Picoclaw interaction patterns where feasible.

### Persistence & Checkpointing

- [ ] **PERS-01**: System persists runtime events and run/session metadata in Postgres for non-guest runs.
- [ ] **PERS-02**: System writes workspace checkpoints to S3 at configured milestones for non-guest workspaces.
- [ ] **PERS-03**: System tracks checkpoint manifest/version and active revision pointer for persistent workspaces.
- [ ] **PERS-04**: System hydrates workspace from latest checkpoint for cold-start restore of persistent workspaces.

### Policy & Security

- [ ] **SECU-01**: System enforces default-deny outbound network policy.
- [ ] **SECU-02**: System enforces tool allowlist policy per user/agent context.
- [ ] **SECU-03**: System injects only scoped secrets required for each run.
- [ ] **SECU-04**: System writes immutable append-only audit events.
- [ ] **SECU-05**: System includes automated policy and isolation boundary tests.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Persistence

- **PERS-05**: Operator can configure retention policy (TTL and max checkpoints) per user/workspace.

### Observability

- **OBSV-01**: System emits structured logs with run/user/workspace correlation IDs.
- **OBSV-02**: System emits distributed traces across API, queue, worker, and sandbox lifecycle.
- **OBSV-03**: System exposes core runtime metrics (queue depth, latency, error rates, lifecycle counts).
- **OBSV-04**: System exposes per-user usage metrics for runs and runtime cost signals.
- **OBSV-05**: System exposes run timeline query APIs for operational debugging.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Organization-first tenancy and billing abstractions | v1 is OSS-first and user-centric for speed and adoption |
| Full business procedure-distillation product UX | Planned as post-v1 milestone after runtime foundation is validated |
| Fully managed hosted offering by this team | v1 targets self-hosted operators |
| Full observability feature set in v1 | Upstream Picoclaw observability is evolving; this project will layer on top later |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AGNT-01 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| AGNT-02 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| AGNT-03 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| AUTH-01 | Phase 1 - Identity and Policy Baseline | Pending |
| AUTH-02 | Phase 1 - Identity and Policy Baseline | Pending |
| AUTH-03 | Phase 1 - Identity and Policy Baseline | Pending |
| AUTH-04 | Phase 4 - Execution Orchestration and Fairness | Pending |
| AUTH-05 | Phase 1 - Identity and Policy Baseline | Pending |
| AUTH-06 | Phase 1 - Identity and Policy Baseline | Pending |
| WORK-01 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| WORK-02 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| WORK-03 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| WORK-04 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| WORK-05 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| WORK-06 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |
| EXEC-01 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EXEC-02 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EXEC-03 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EXEC-04 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EXEC-05 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EXEC-06 | Phase 4 - Execution Orchestration and Fairness | Pending |
| EVNT-01 | Phase 5 - Typed Event Streaming API | Pending |
| EVNT-02 | Phase 5 - Typed Event Streaming API | Pending |
| EVNT-03 | Phase 5 - Typed Event Streaming API | Pending |
| EVNT-04 | Phase 5 - Typed Event Streaming API | Pending |
| EVNT-05 | Phase 5 - Typed Event Streaming API | Pending |
| EVNT-06 | Phase 5 - Typed Event Streaming API | Pending |
| PERS-01 | Phase 3 - Persistence and Checkpoint Recovery | Pending |
| PERS-02 | Phase 3 - Persistence and Checkpoint Recovery | Pending |
| PERS-03 | Phase 3 - Persistence and Checkpoint Recovery | Pending |
| PERS-04 | Phase 3 - Persistence and Checkpoint Recovery | Pending |
| SECU-01 | Phase 1 - Identity and Policy Baseline | Pending |
| SECU-02 | Phase 1 - Identity and Policy Baseline | Pending |
| SECU-03 | Phase 1 - Identity and Policy Baseline | Pending |
| SECU-04 | Phase 3 - Persistence and Checkpoint Recovery | Pending |
| SECU-05 | Phase 2 - Workspace Lifecycle and Agent Pack Portability | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 after adding AUTH-06 guest identity policy*
