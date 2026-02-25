# Roadmap: Picoclaw Multi-Tenant OSS Runtime

**Depth:** standard
**Created:** 2026-02-23

## Overview

This roadmap is derived directly from the v1 requirements for a self-hosted, user-centric multi-tenant Picoclaw runtime. Phases are ordered by dependency so each phase unlocks a complete, testable user-facing capability and de-risks the next stage. Coverage is strict: every v1 requirement maps to exactly one phase, including the OSS workflow from template docs/files to agent pack registration and profile-portable execution.

Commercial invariant for v1: define templates -> create agent pack -> infrastructure handles scale.

```mermaid
flowchart LR
  P1[Phase 1\nIdentity and Policy Baseline] --> P2[Phase 2\nWorkspace Lifecycle and Agent Pack Portability]
  P2 --> P3[Phase 3\nPersistence and Checkpoint Recovery]
  P3 --> P4[Phase 4\nExecution Orchestration]
  P4 --> P5[Phase 5\nTyped Event Streaming API]
```

## Phase Structure

| Phase | Goal | Dependencies | Requirements |
|------|------|--------------|--------------|
| 1 - Identity and Policy Baseline | Users can authenticate requests safely and execute only within authorized, policy-constrained boundaries. | None | AUTH-01, AUTH-02, AUTH-03, AUTH-05, AUTH-06, SECU-01, SECU-02, SECU-03 |
| 2 - Workspace Lifecycle and Agent Pack Portability | Each user gets a durable workspace and can move from template scaffold to registered agent pack that runs in local Docker Compose and BYOC profiles without manual infra wiring. | Phase 1 | AGNT-01, AGNT-02, AGNT-03, WORK-01, WORK-02, WORK-03, WORK-04, WORK-05, WORK-06, SECU-05 |
| 3 - Persistence and Checkpoint Recovery | Runtime state is durably stored and recoverable through milestone checkpoints with immutable audit history. | Phase 2 | PERS-01, PERS-02, PERS-03, PERS-04, SECU-04 |
| 4 - Execution Orchestration and Fairness | Runs execute reliably under retries/cancellation while preserving ordering per workspace and fairness across users. | Phase 1, Phase 2, Phase 3 | AUTH-04, EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06 |
| 5 - Typed Event Streaming API | Clients can consume real-time typed runtime events and fetch final run outputs in Picoclaw-aligned contracts. | Phase 3, Phase 4 | EVNT-01, EVNT-02, EVNT-03, EVNT-04, EVNT-05, EVNT-06 |

## Phase Details

### Phase 1 - Identity and Policy Baseline

**Goal:** Users can authenticate requests safely and execute only within authorized, policy-constrained boundaries.

**Dependencies:** None

**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-05, AUTH-06, SECU-01, SECU-02, SECU-03

**Success Criteria (observable):**
1. A user can call the API with a personal API key and receive authorized responses only for valid credentials.
2. A user or operator can rotate or revoke an API key, and revoked keys fail subsequent requests.
3. A user can read/write only resources in their own workspace and cannot access another user's workspace data.
4. An operator can assign owner/member role behavior and observe access differences in API outcomes.
5. Requests without explicit user identity are assigned a random guest identity and execute in guest mode without persistent storage.
6. Runtime runs enforce default-deny network egress, tool allowlists, and scoped secret injection per run context.

**Plans:** 9 plans

Plans:
- [x] 01-01-PLAN.md — Bootstrap FastAPI/DB foundation and RLS-ready schema baseline.
- [x] 01-02-PLAN.md — Implement personal API key authentication with rotate/revoke lifecycle.
- [x] 01-03-PLAN.md — Enforce workspace isolation and owner/member authorization behavior.
- [x] 01-04-PLAN.md — Implement guest identity mode and default-deny runtime policy controls.
- [x] 01-05-PLAN.md — Validate Phase 1 with acceptance and security regression suites.
- [x] 01-06-PLAN.md — Close RLS context propagation gap identified by verification.
- [x] 01-07-PLAN.md — Close membership-backed role resolution gap identified by verification.
- [x] 01-08-PLAN.md — Close runtime policy enforcement and structured denial gap.
- [x] 01-09-PLAN.md — Close member workspace resource mutation authorization gap.

### Phase 2 - Workspace Lifecycle and Agent Pack Portability

**Goal:** Each user gets a durable workspace and can move from template scaffold to registered agent pack that runs in local Docker Compose and BYOC profiles without manual infra wiring.

**Dependencies:** Phase 1

**Requirements:** AGNT-01, AGNT-02, AGNT-03, WORK-01, WORK-02, WORK-03, WORK-04, WORK-05, WORK-06, SECU-05

**Success Criteria (observable):**
1. A user sees continuity across sessions because the same persistent workspace is reused.
2. A user can bootstrap a new agent workspace from filesystem templates (`AGENT.md`, `SOUL.md`, `IDENTITY.md`, `skills/`) and register that folder as an agent pack without manual infrastructure wiring.
3. The same registered agent pack runs with equivalent semantics in local Docker Compose and BYOC profiles (for example Postgres, queue, and S3-compatible dependencies), with Daytona Cloud as the recommended fast-path BYOC runtime for v1.
4. A request routes to an already active healthy sandbox when one exists for that workspace, or hydrates/creates a sandbox with workspace attached when none exists.
5. Concurrent write attempts for the same workspace are serialized, unhealthy sandboxes are excluded from routing, idle sandboxes auto-stop by TTL, and policy/isolation boundary tests pass in CI.

**Plans:** 12 plans

Plans:
- [x] 02-01-PLAN.md — Add Phase 2 schema foundation for leases, sandboxes, and path-linked agent packs.
- [x] 02-02-PLAN.md — Implement provider adapter abstraction for local compose and Daytona parity semantics.
- [x] 02-03-PLAN.md — Build workspace lifecycle services for durable reuse, lease serialization, and health-aware routing.
- [x] 02-04-PLAN.md — Implement template scaffold, validation checklist, and path-linked pack registration with stale detection.
- [x] 02-05-PLAN.md — Expose Phase 2 API routes and lock behavior with acceptance and security regression suites.
- [x] 02-06-PLAN.md — Close workspace route UUID ownership normalization and resolve endpoint auth contract gaps.
- [x] 02-07-PLAN.md — Fix scaffold absolute-path handling and pack/provider portability contract mismatches.
- [x] 02-08-PLAN.md — Re-green Phase 2 acceptance plus SECU-05 suites and capture final gap-closure evidence.
- [x] 02-09-PLAN.md — Wire run-to-provider `agent_pack_id` propagation with fail-closed validation before provisioning.
- [x] 02-10-PLAN.md — Implement provider pack-binding parity and close UAT Test 4 with end-to-end acceptance coverage.
- [ ] 02-11-PLAN.md — Replace Daytona simulated adapter behavior with real API-backed lifecycle interactions.
- [ ] 02-12-PLAN.md — Add acceptance/security evidence for Daytona API-backed routing and fail-closed semantics.

### Phase 3 - Persistence and Checkpoint Recovery

**Goal:** Runtime state is durably stored and recoverable through milestone checkpoints with immutable audit history.

**Dependencies:** Phase 2

**Requirements:** PERS-01, PERS-02, PERS-03, PERS-04, SECU-04

**Success Criteria (observable):**
1. Run/session metadata and runtime events are queryable from Postgres after execution.
2. Workspace checkpoints are written to S3-compatible storage at configured milestone boundaries.
3. The system exposes checkpoint manifest/version and a clear active revision pointer for each workspace.
4. Cold-start restore hydrates a workspace from its latest checkpoint and resumes expected state.
5. Audit events are append-only and immutable once recorded.

### Phase 4 - Execution Orchestration and Fairness

**Goal:** Runs execute reliably under retries/cancellation while preserving ordering per workspace and fairness across users.

**Dependencies:** Phase 1, Phase 2, Phase 3

**Requirements:** AUTH-04, EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06

**Success Criteria (observable):**
1. Requests for the same workspace run in order without overtaking.
2. Requests for different users run in parallel without cross-user blocking.
3. Retried client requests with the same idempotency key do not create duplicate run side effects.
4. Transient failures retry with bounded backoff, and exhausted retries move jobs to dead-letter state.
5. A user or operator can cancel an active run, and per-user queue/concurrency caps prevent noisy-neighbor starvation.

### Phase 5 - Typed Event Streaming API

**Goal:** Clients can consume real-time typed runtime events and fetch final run outputs in Picoclaw-aligned contracts.

**Dependencies:** Phase 3, Phase 4

**Requirements:** EVNT-01, EVNT-02, EVNT-03, EVNT-04, EVNT-05, EVNT-06

**Success Criteria (observable):**
1. A client can subscribe to an active run over SSE and receive ordered runtime updates.
2. A client can subscribe to the same run over WebSocket with equivalent event semantics.
3. Streams emit the typed event envelope (`message`, `tool_call`, `tool_result`, `ui_patch`, `state_update`, `error`).
4. Streams emit run lifecycle states (`queued`, `running`, `cancelled`, `completed`, `failed`).
5. After completion, a client can fetch final transcript and artifact snapshot using Picoclaw-aligned event contracts.

## Requirement Coverage

**v1 requirements:** 36
**Mapped:** 36
**Unmapped:** 0

```mermaid
flowchart TD
  subgraph P1[Phase 1]
    AUTH1[AUTH-01..03, AUTH-05..06]
    SECU1[SECU-01..03]
  end

  subgraph P2[Phase 2]
    AGNT1[AGNT-01..03]
    WORK1[WORK-01..06]
    SECU5[SECU-05]
  end

  subgraph P3[Phase 3]
    PERS1[PERS-01..04]
    SECU4[SECU-04]
  end

  subgraph P4[Phase 4]
    AUTH4[AUTH-04]
    EXEC1[EXEC-01..06]
  end

  subgraph P5[Phase 5]
    EVNT1[EVNT-01..06]
  end
```

## Progress

| Phase | Status | Completion |
|------|--------|------------|
| 1 - Identity and Policy Baseline | Complete | 100% |
| 2 - Workspace Lifecycle and Agent Pack Portability | Complete | 100% |
| 3 - Persistence and Checkpoint Recovery | Not Started | 0% |
| 4 - Execution Orchestration and Fairness | Not Started | 0% |
| 5 - Typed Event Streaming API | Not Started | 0% |

**Overall Progress:** 40%
