# Phase 3: Persistence and Checkpoint Recovery - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Persist non-guest runtime events plus run/session metadata, write workspace checkpoints to S3-compatible storage, track manifest/version with an active revision pointer, restore from latest checkpoint on cold start, and keep audit history append-only and immutable.

</domain>

<decisions>
## Implementation Decisions

### Sandbox and Session Topology
- 1 user maps to 1 sandbox.
- Multi-user means multi-sandbox.
- 1 user with multiple sessions stays in the same sandbox.

### Cold-Start Restore
- If restore is in progress, acknowledge run requests as queued with `run_id` and `restoring` state.
- Restore readiness requires runtime health-check success, not only files restored.
- If latest checkpoint is unusable, fallback to the previous valid checkpoint.
- If restore fails, retry restore once, then continue execution without memory/session data (static identity mount still present).
- If restore takes too long, return timeout with retry guidance.
- Restore progress visibility stays coarse (`state` only).

### Checkpoint Scope and Triggering
- Checkpoint data means memory/session state only.
- Static identity files are not checkpoint content; they are always mounted during sandbox creation (`AGENT.md`, `SOUL.md`, `IDENTITY.md`, `skills/`).
- Checkpoint policy is hybrid (milestone-based plus interval safety checkpoints).
- No manual checkpoint trigger in this phase.
- Checkpoint status exposure is last checkpoint state (latest status/timestamp oriented).

### Restore Transparency
- Checkpoint fallback events are visible in audit history (not required in immediate run response).

### Gateway and Ownership
- Each sandbox exposes a gateway endpoint for sending runtime messages.
- The orchestrator owns checkpointing behavior and lifecycle.

### Revision Pointer Rules
- Active revision pointer auto-advances to the newest successful checkpoint.
- Only operators can change the active revision pointer.
- Rollback to older revisions is not allowed in Phase 3.
- Pointer changes are visible in audit history only.

### Audit History Surface
- First-class audit view is run timeline.
- Minimum event detail is operational: event type, timestamp, actor, workspace, and reason.
- Immutable-write attempts are hard rejected.
- Full audit detail access is operator-only in Phase 3.

### OpenCode's Discretion
- Checkpoint interval duration and milestone boundary definitions.
- Degraded-mode policy when background checkpointing remains unhealthy.
- Exact API surface and filters for run timeline audit reads.
- Reason-code taxonomy and remediation message wording.

</decisions>

<specifics>
## Specific Ideas

- "Checkpoint" should be treated as workspace filesystem/runtime-state persistence aligned with Picoclaw semantics, not metadata-only persistence.
- Explicit separation: checkpoints restore only dynamic memory/session state; identity/skills files are static mounts during sandbox provisioning.
- OSS runtime intent: quickly deploy a specific agent with packed static identity files, while checkpoint restore only rehydrates memory/session state.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 03-persistence-and-checkpoint-recovery*
*Context gathered: 2026-02-26*
