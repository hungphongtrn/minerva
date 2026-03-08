# Research Summary

**Domain:** Self-hosted multi-tenant agent runtime (Picoclaw-compatible)
**Synthesized:** 2026-02-23

## Executive Summary

Research converges on a security-first, durability-first runtime: this is a multi-tenant control plane plus isolated execution data plane, not just an "agent runner." Teams that succeed in this domain enforce tenant context at every hop (API, queue, worker, DB, checkpoints), treat sandboxing as defense-in-depth (not a complete boundary), and make checkpointed recovery + ordered event streaming a core product behavior rather than an add-on.

The recommended implementation path is opinionated and pragmatic: Python 3.13 + FastAPI + Pydantic for control-plane contracts, Postgres for authoritative metadata and tenancy boundaries, NATS JetStream for durable dispatch/event fan-out, Daytona for sandbox lifecycle, and S3-compatible object storage for immutable checkpoint artifacts. Architecturally, the strongest default is one workspace per user, immutable checkpoint revisions, explicit workspace leases, and a control-plane/data-plane split with policy enforcement before and during execution.

Primary delivery risk is not missing a feature; it is breaking invariants under concurrency: losing tenant identity across async boundaries, diverging checkpoint state from event history, and retry-driven duplicate side effects. The mitigation strategy is to front-load identity and policy envelopes, enforce idempotency and ordering contracts early, and defer broad differentiators (multi-backend sandbox abstraction, full policy DSL, BI dashboards) until core safety and recovery paths are proven in pilot load tests.

## Key Findings

### Stack

- **Python 3.13.x + FastAPI 0.131.x + Pydantic 2.12.x:** best fit for typed control-plane APIs and event contracts with fast implementation velocity.
- **Postgres 17.x (18.x after soak):** most reliable transactional source of truth for tenant/workspace/run metadata; avoid queue-on-DB anti-patterns.
- **NATS 2.12.x + JetStream:** strong fit for at-least-once work dispatch, durable streams, replay, and backpressure in mixed Python/Go worker ecosystems.
- **Daytona 0.144.x + S3-compatible storage (Ceph RGW preferred):** cleanly maps to sandbox lifecycle + checkpoint durability requirements.
- **Critical version constraints:** FastAPI `0.131.x` with Pydantic `2.12.x`, SQLAlchemy `2.0.x` with Alembic `1.18.x`, nats-py `2.13.x` with NATS `2.12.x`.

### Features

- **Must-have (table stakes):** tenant/workspace isolation, tenant-scoped AuthN/AuthZ, sandbox lifecycle controls, durable checkpoint/restore, typed runtime event streaming, policy controls for network/tools, audit/observability, and per-tenant quotas.
- **Should-have (differentiators):** deterministic replay/time-travel debugging, snapshot-based warm starts, tenant-aware unified policy surface, usage/cost telemetry, and eventually multi-backend sandbox portability.
- **Defer to v2+:** full policy-as-code language, multi-backend isolation productization, enterprise-grade org/billing hierarchy, and BI-heavy governance dashboards.
- **Strong anti-features for v1:** no default-open egress, no shared global memory/workspace across tenants, no flat global RBAC, no infinite sandbox lifetimes, no mutable/non-immutable audit history.

### Architecture

- **Core architecture:** control plane (identity, policy, orchestration) separated from data plane (scheduler, workers, sandbox execution).
- **State model:** one workspace per user identity, explicit workspace lease/lock, immutable checkpoints with atomic pointer updates.
- **Canonical runtime flow:** authenticate and resolve tenant -> authorize -> resolve/attach or hydrate workspace -> enqueue run -> stream ordered events -> write checkpoint revision -> finalize run metadata.
- **Component boundaries:** API owns transport only; orchestrator owns lifecycle/idempotency; workspace manager owns hydrate/lease/checkpoint plumbing; workers execute tools/events only; policy engine decides allow/deny.
- **Build-order insight:** identity and policy envelope must land before metadata, which must land before workspace hydration and execution paths.

### Pitfalls

- **Tenant context loss across async boundaries:** make `tenant_id` + `workspace_id` mandatory in all internal envelopes and reject missing context at every boundary.
- **Checkpoint/event divergence:** enforce a monotonic revision contract and atomic commit markers between object writes and metadata pointers.
- **Retry duplicates from at-least-once delivery:** require idempotency keys and dedupe tables for all externally visible side effects.
- **Noisy-neighbor starvation:** implement per-tenant concurrency caps and fair scheduling before scaling tenant load.
- **Isolation theater (container-only security):** enforce default-deny egress, least-privilege runtime profiles, scoped secrets, and policy tests.

## Implications for Roadmap

Suggested phase structure: **6 phases**

1. **Phase 1 - Identity and Isolation Baseline**
   - **Rationale:** all downstream controls are invalid without trustworthy tenant context and hardened sandbox policy defaults.
   - **Delivers:** tenant resolver, tenant-scoped AuthN/AuthZ model, policy enforcement envelope, egress/tool guardrail primitives, base workspace ownership model.
   - **Feature mapping:** table stakes isolation + AuthZ + network/tool policy.
   - **Pitfalls to avoid:** context loss (#1), container-only assumptions (#2).

2. **Phase 2 - Durable Workspace and Execution Semantics**
   - **Rationale:** resumability and deterministic recovery are core runtime value and prerequisite for advanced debugging.
   - **Delivers:** workspace manager, lease model, checkpoint manifest/revision system, hydrate/attach flow, lifecycle state machine.
   - **Feature mapping:** sandbox lifecycle + durable execution/checkpointing.
   - **Pitfalls to avoid:** checkpoint ordering divergence (#3), volume misuse (#6).

3. **Phase 3 - Reliable Orchestration and Queueing**
   - **Rationale:** correctness under retries and multi-tenant load must be solved before broad pilot expansion.
   - **Delivers:** NATS JetStream dispatch, idempotent run handlers, retry/DLQ strategy, fair scheduling and per-tenant concurrency controls.
   - **Feature mapping:** quotas/noisy-neighbor controls + reliable run dispatch.
   - **Pitfalls to avoid:** exactly-once assumptions (#4), starvation under shared queues (#5).

4. **Phase 4 - Event Streaming and Debuggability**
   - **Rationale:** real-time UX and operator trust require ordered, typed events tied to run/workspace state.
   - **Delivers:** canonical event schema, SSE/WS stream gateway, replay window, run timeline inspection.
   - **Feature mapping:** typed event streaming (table stakes), foundation for replay/time-travel differentiator.
   - **Pitfalls to avoid:** schema drift and ordering inconsistencies (extends #3 controls).

5. **Phase 5 - Observability, Audit, and Lifecycle Reconciliation**
   - **Rationale:** pilots fail operationally without tenant-filterable observability and automated cleanup/reconciliation.
   - **Delivers:** tenant-safe OTel traces/logs/metrics, immutable audit trail APIs, reconciler for sandbox/workspace lifecycle convergence, GC jobs.
   - **Feature mapping:** observability/audit table stakes + runtime hygiene.
   - **Pitfalls to avoid:** metrics cardinality explosion (#8), incomplete cleanup/orphans (#9).

6. **Phase 6 - Pilot Hardening and Differentiators**
   - **Rationale:** only after core invariants pass should the project invest in advanced replay, warm starts, and enterprise policy ergonomics.
   - **Delivers:** deterministic replay UX, snapshot warm-start optimization, stricter snapshot compatibility gates, early usage telemetry views.
   - **Feature mapping:** replay/time-travel, warm starts, cost telemetry differentiators.
   - **Pitfalls to avoid:** snapshot/image drift (#10), late-discovered reproducibility regressions.

### Research Flags

- **Needs `/gsd-research-phase`:**
  - Phase 3 (scheduler fairness algorithms and queue partitioning strategy by tenant profile).
  - Phase 6 (deterministic replay guarantees and snapshot compatibility gates at scale).
- **Likely skip deep research (patterns are mature):**
  - Phase 1 (tenant context propagation + policy envelope patterns are well-documented).
  - Phase 2 (immutable checkpointing and workspace lease patterns are well-established).
  - Phase 5 baseline observability/audit mechanics (focus should be implementation quality, not novelty).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Version guidance and component choices are anchored in current official releases/docs; minor package-version drift risk only. |
| Features | MEDIUM-HIGH | Table-stakes consensus is strong across platform docs; differentiator prioritization is partly synthesis-driven. |
| Architecture | MEDIUM-HIGH | Control/data-plane split and checkpoint-driven lifecycle are strongly supported; exact service decomposition can vary by team size. |
| Pitfalls | HIGH | Failure modes are consistent with distributed systems + multi-tenant SaaS guidance and include concrete preventions/tests. |

Overall confidence: **MEDIUM-HIGH**.

## Gaps to Address During Planning

- Define explicit tenant model scope for v1 (single-tenant user workspaces vs early org hierarchy) to prevent permission model churn.
- Choose fairness policy details (weighted fair queueing vs partition-per-tenant lanes) and associated SLO targets before Phase 3 build-out.
- Pin the checkpoint schema/versioning contract early, including backwards-compatibility policy for replay and restore.
- Establish initial capacity assumptions (expected concurrent runs, checkpoint sizes, warm pool budget) to avoid premature or under-scaled architecture.
- Decide minimal compliance posture for pilot (audit retention duration, encryption/KMS baseline, incident response expectations).

## Sources

Aggregated from the four research documents:

- Kubernetes multi-tenancy guidance
- AWS SaaS authorization (PDP/PEP) prescriptive guidance
- Temporal workflow durability documentation
- OpenAI Agents SDK running/streaming/session docs
- LangGraph persistence/checkpointing docs
- Daytona docs (sandboxes, snapshots, network limits, volumes, audit logs)
- PostgreSQL docs (versioning policy and row-level security)
- NATS/JetStream docs and release notes
- Ceph and S3/object storage references
- OpenTelemetry and Prometheus observability guidance

For full source URLs and confidence tags, see:
- `.planning/research/STACK.md`
- `.planning/research/FEATURES.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`
