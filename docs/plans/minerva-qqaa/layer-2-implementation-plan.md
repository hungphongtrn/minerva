# Minerva QQAA Layer 2 Implementation Plan

Layer 2 turns the layer 1 proposal set into an implementation-ready plan for `minerva-qqaa` and child bean `minerva-03i3`.

## Goal

Implement a pi-shaped hosted session runtime in Minerva without changing end-user agent behavior by: making Postgres the durable source of truth for sessions, entries, runs, bindings, and replay events; moving run execution behind a session runtime adapter boundary; materializing runtime resources into Daytona workspaces before execution; extending HTTP/SSE contracts to be session-aware while keeping current run endpoints as a compatibility layer; and generating pi-shaped exports from Postgres-backed durable entries rather than from transient stream data.

## References

- Bean: [`minerva-qqaa`](../../../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)
- Bean: [`minerva-03i3`](../../../.beans/minerva-03i3--produce-layer-2-implementation-planning-for-minerv.md)
- Proposal index: [`docs/plans/minerva-qqaa/INDEX.md`](./INDEX.md)
- Plans index: [`docs/plans/minerva-qqaa/INDEX.md`](./INDEX.md)
- Current runtime: [`services/orchestrator/src/runtime/run-execution.service.ts`](../../../services/orchestrator/src/runtime/run-execution.service.ts)
- Current run lifecycle: [`services/orchestrator/src/services/run-manager.ts`](../../../services/orchestrator/src/services/run-manager.ts)
- Current sandbox adapter: [`services/orchestrator/src/sandbox/adapter.ts`](../../../services/orchestrator/src/sandbox/adapter.ts)
- Current Prisma schema: [`services/orchestrator/prisma/schema.prisma`](../../../services/orchestrator/prisma/schema.prisma)
- Current persistence interfaces: [`services/orchestrator/src/repo/runtime-persistence.types.ts`](../../../services/orchestrator/src/repo/runtime-persistence.types.ts)

## Planning principles

1. Preserve current agent behavior before expanding capability.
2. Prefer additive, compatibility-safe migrations over wide rewrites.
3. Keep durable session history append-oriented.
4. Treat run streaming and durable history as separate concerns.
5. Keep Daytona details below a Minerva-owned coding runtime boundary.
6. Materialize runtime-visible files inside the sandbox instead of reading from orchestrator host paths at execution time.

## 1. Postgres schema and repository plan

The current Prisma schema is a useful starting point, but it still reflects a v0 run-centric model. Layer 2 should keep the existing tables where they help and evolve them into a session-first schema.

### 1.1 Canonical tables

#### `sessions`
Keep and extend the current table. Required columns: `id`, `tenant_id`, `subject_id`, `owner_key`, `agent_pack_id`, `workspace_binding_id`, `sandbox_binding_id`, `status` (`active`, `archived`, `errored`), `display_name`, `current_leaf_entry_id`, `current_run_id` nullable, `last_active_at`, `export_version`, `created_at`, `updated_at`. Required indexes: `(owner_key, agent_pack_id, last_active_at desc)`, `(workspace_binding_id)`, `(sandbox_binding_id)`, `(status, last_active_at desc)`.

#### `session_entries`
Reshape the table from message-only storage into a general durable entry log. Required columns: `id`, `session_id`, `parent_entry_id`, `sequence`, `entry_type` (`message`, `tool_result`, `model_change`, `thinking_level_change`, `label`, `session_info`, `compaction`, `branch_summary`, `custom`), `author_kind` (`system`, `user`, `assistant`, `tool`, `runtime`, `extension`), `payload_json`, `context_inclusion`, `run_id` nullable, `created_at`. Required indexes: unique `(session_id, sequence)`, `(session_id, parent_entry_id)`, `(session_id, run_id, sequence)`, `(session_id, created_at)`. Rename `message_json` to `payload_json`, replace the narrow `SessionEntryType` enum, and preserve `parent_entry_id` even while public branching stays hidden.

#### `runs`
Keep `runs` as execution-control records subordinate to sessions. Required additions: `session_id` becomes expected for new work, `request_kind` (`prompt`, `follow_up`, `resume`, `steer`, `maintenance`), `requested_entry_id` nullable, `sandbox_binding_id` nullable, `workspace_binding_id` nullable, `error_code` nullable, `command_envelope_json` nullable. Required indexes: `(session_id, created_at desc)`, `(owner_key, state, created_at desc)`, `(workspace_binding_id, created_at desc)`.

#### `run_attempts`
Keep as the per-execution-attempt table. Required additions: `sandbox_id` nullable, `workspace_id` nullable, `failure_stage` nullable (`lease`, `sandbox`, `materialize`, `agent_loop`, `persist`, `stream`), `error_code` nullable.

#### `replay_events`
Keep, but treat it as replay/observability storage instead of primary history. Required additions: `durability_class` (`transient_replayable`, `derived_from_entry`, `run_lifecycle`), `session_sequence` nullable when the event maps to a durable entry, and `delivery_group` nullable for session stream multiplexing. Required indexes: unique `(run_id, seq)`, `(session_id, created_at)`, `(tenant_id, subject_id, session_id, seq)`, `(created_at)` for retention cleanup.

#### `sandbox_bindings`
Add a stable per-user-agent binding table with columns `id`, `tenant_id`, `subject_id`, `owner_key`, `agent_pack_id`, `binding_key`, `daytona_sandbox_id` nullable, `state` (`cold`, `provisioning`, `warm`, `expiring`, `disposed`, `errored`), `network_policy`, `last_used_at`, `expires_at` nullable, `created_at`, `updated_at`. Indexes: unique `(binding_key)`, `(owner_key, agent_pack_id)`, `(state, expires_at)`.

#### `workspace_bindings`
Add a durable workspace mapping table with columns `id`, `sandbox_binding_id`, `workspace_key`, `workspace_id` nullable, `root_path`, `runtime_root_path`, `state` (`missing`, `materializing`, `ready`, `draining`, `errored`), `applied_manifest_hash` nullable, `applied_manifest_version` nullable, `last_materialized_at` nullable, `created_at`, `updated_at`. Indexes: unique `(workspace_key)`, unique `(sandbox_binding_id)`, `(state, updated_at)`.

#### `resource_manifests`
Add a table recording exactly what runtime-visible resources were materialized. Columns: `id`, `workspace_binding_id`, `manifest_hash`, `manifest_version`, `source_kind` (`agent_pack`, `platform_default`, `generated`), `manifest_json`, `created_at`. Indexes: unique `(workspace_binding_id, manifest_hash)`, `(workspace_binding_id, created_at desc)`.

### 1.2 Repository split

Replace the broad type-only storage contracts in `src/repo/runtime-persistence.types.ts` with concrete repository modules under `services/orchestrator/src/repo/`.

Recommended files:
- `src/repo/session-repository.ts`
- `src/repo/session-entry-repository.ts`
- `src/repo/run-repository.ts`
- `src/repo/run-attempt-repository.ts`
- `src/repo/replay-event-repository.ts`
- `src/repo/sandbox-binding-repository.ts`
- `src/repo/workspace-binding-repository.ts`
- `src/repo/resource-manifest-repository.ts`
- `src/repo/transaction-runner.ts`
- `src/repo/mappers/*.ts`

Repository responsibilities:
- session repository: create/find session, update pointers, resolve default session for owner+agent
- session entry repository: append entries, fetch lineage, fetch exportable path, fetch current leaf path
- run repository: create run, transition lifecycle, query active/current run for session
- run attempt repository: create/update attempt and infrastructure error stage
- replay event repository: append and replay ordered event sequences
- sandbox/workspace binding repositories: resolve or create durable bindings, update lifecycle states, update idle expiry
- resource manifest repository: store/retrieve last applied manifest hash and manifest payload

Transaction plan: use one Prisma-backed `TransactionRunner` abstraction so runtime operations can append durable entries, advance session leaf state, and record run lifecycle changes atomically.

### 1.3 Migration ordering

1. Add missing columns to `sessions`, `runs`, `run_attempts`, and `replay_events`.
2. Widen `session_entries` to generic payload/entry typing.
3. Add `sandbox_bindings`, `workspace_bindings`, and `resource_manifests`.
4. Backfill existing run/session rows where possible.
5. Switch runtime reads/writes from in-memory repository paths to Prisma repositories.

## 2. Session runtime adapter boundaries

The current `RunExecutionService` mixes API validation, queue orchestration, workspace acquisition, pack loading, direct pi-agent construction, and SSE emission. Layer 2 should split this into session-first boundaries.

### 2.1 Target service graph

Recommended module layout under `services/orchestrator/src/session/`:
- `session.module.ts`
- `session-command.service.ts`
- `session-runtime.service.ts`
- `session-context.service.ts`
- `session-export.service.ts`
- `session-errors.ts`
- `contracts.ts`

Supporting infrastructure modules:
- `src/runtime/runtime-event-recorder.service.ts`
- `src/runtime/runtime-event-broadcaster.service.ts`
- `src/sandbox/sandbox-binding.service.ts`
- `src/sandbox/workspace-materializer.service.ts`
- `src/resources/resource-manifest.service.ts`
- `src/resources/resource-source.service.ts`

### 2.2 Boundary responsibilities

#### `SessionCommandService`
Entry point from HTTP controllers. Responsibilities: create or resolve session, validate request envelope and consumer-safe rules, create run row and run attempt row, enqueue run execution, and map legacy `POST /runs` into a session-backed command.

#### `SessionRuntimeService`
Hosted equivalent of a pi `AgentSession`. Responsibilities: load session and current leaf state, reconstruct context messages/settings from `session_entries`, obtain sandbox/workspace bindings, invoke resource materialization, create coding tool surface against a runtime-scoped adapter, invoke pi-agent-core with reconstructed initial state, convert finalized outputs into durable entries, and coordinate cancellation/timeout semantics.
Recommended public methods:
- `createSession(command)`
- `executePrompt(command)`
- `executeFollowUp(command)`
- `resumeSession(command)`
- `cancelRun(command)`
- `getSession(sessionId)`
- `exportSession(sessionId)`

#### `SessionContextService`
Responsibilities: fetch lineage from `session_entries`, apply context inclusion rules, derive active model and thinking level, and emit normalized pi-core input messages plus runtime metadata.

#### `RuntimeEventRecorderService`
Responsibilities: append replayable events to `replay_events`, stamp `session_id`, `run_id`, `attempt_id`, and `seq`, and classify transient vs durable-derived events.

#### `RuntimeEventBroadcasterService`
Responsibilities: publish live SSE after persistence when required, serve replay reads from durable storage instead of in-memory only, and keep temporary in-memory fanout for active connections only.

### 2.3 Refactor boundary for existing classes

- `RunExecutionService`: shrink into orchestration glue and compatibility shims, then gradually replace with `SessionCommandService`
- `RunManager`: keep queue/lease/timeout concerns, but remove responsibility for being the primary persistence abstraction
- `SSEService`: keep connection fanout behavior, but move sequencing and replay source of truth into Postgres-backed event recorder/replayer
- `ToolRegistry`: reuse conceptually, but instantiate from a runtime-scoped coding adapter rather than directly from `ISandboxAdapter`

## 3. Sandbox binding and resource materialization flow

### 3.1 Binding model

Use the approved binding key: `binding_key = tenant_id + ':' + subject_id + ':' + agent_pack_id`.
Flow:
1. session resolves `sandbox_binding`
2. binding resolves or creates `workspace_binding`
3. run attempt records the resolved sandbox/workspace ids
4. runtime updates `last_used_at` on every successful command
5. idle cleanup transitions bindings to `expiring` then `disposed`

### 3.2 Runtime-visible filesystem layout

Materialize a stable runtime root inside the Daytona workspace.
Recommended layout:
- `/.minerva/runtime/AGENTS.md`
- `/.minerva/runtime/.agents/skills/...`
- `/.minerva/runtime/prompts/...`
- `/.minerva/runtime/extensions/...`
- `/.minerva/runtime/session/metadata.json`
- `/.minerva/runtime/session/resources-manifest.json`

The session runtime should point resource discovery at this runtime root, not at the orchestrator host pack directory.

### 3.3 Materialization sequence

For each run attempt:
1. resolve binding and active workspace
2. acquire a short-lived materialization lock keyed by `workspace_binding_id`
3. build a resource manifest from pack assets, generated compatibility files, and platform defaults
4. hash the manifest content
5. compare against `workspace_bindings.applied_manifest_hash`
6. if unchanged and workspace is `ready`, skip writes
7. if changed or missing, mark workspace binding `materializing`, write files into the runtime root, write `resources-manifest.json`, update `resource_manifests`, and update workspace binding hash/version/state=`ready`
8. release lock and continue to agent execution

### 3.4 Failure contract

If materialization fails: write `run_attempts.failure_stage = materialize`; emit replay event `workspace_materialization_failed`; emit stable API error code `WORKSPACE_MATERIALIZATION_FAILED`; and keep session durable history untouched unless a user-visible durable entry has already been finalized.

### 3.5 Idle cleanup plan

A later worker or cron slice should query `sandbox_bindings` where `expires_at < now()` and `state in ('warm','expiring')`, dispose the sandbox in Daytona, mark the binding `disposed`, and leave session history intact so resume recreates infrastructure on demand.

## 4. HTTP and SSE contract changes

### 4.1 HTTP additions

Add new controllers under `services/orchestrator/src/sessions/` while keeping `api/v0/runs` as a compatibility facade.
Recommended endpoints:
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/:sessionId`
- `POST /api/v1/sessions/:sessionId/runs`
- `GET /api/v1/sessions/:sessionId/stream`
- `GET /api/v1/sessions/:sessionId/export`
- `POST /api/v1/runs` as a compatibility alias that internally resolves a session first

Recommended request shape for create/resolve session:
```json
{
  "agentPackId": "default",
  "sessionMode": "default_for_owner_agent"
}
```
Recommended request shape for session run execution:
```json
{
  "kind": "prompt",
  "prompt": "Write a hello world program in Python",
  "maxDurationMs": 600000
}
```
Recommended response shape for `POST /sessions/:sessionId/runs`:
```json
{
  "sessionId": "ses_...",
  "runId": "run_...",
  "state": "queued",
  "queuePosition": 0,
  "createdAt": "2026-03-12T07:00:00.000Z"
}
```

### 4.2 Compatibility rules for existing run endpoints

`POST /api/v0/runs` should resolve or create the default session for `(owner_key, agent_pack_id)`, create a run under that session, and return the current run-centric payload plus `sessionId`. `GET /api/v0/runs/:runId` should include existing run fields plus `sessionId` and optionally `requestKind`.

### 4.3 SSE envelope changes

Extend the current envelope in `docs/api/sse-schema.md` to:
```ts
interface HostedRuntimeEvent<TPayload> {
  type: string;
  run_id: string;
  session_id: string;
  ts: string;
  seq: number;
  payload: TPayload;
}
```
Rules:
- `session_id` is mandatory for all new replayed events
- `seq` remains monotonic per run for v1, but every row stores `session_id` to allow session-level replay later
- `stream_connected` should report both `run_state` and `session_state`
- live-only progress events may remain transient, but terminal events and durable-derived message boundaries must be replayable from Postgres

### 4.4 New hosted events

Keep existing pi-shaped events and add hosted extensions only where needed: `session_resolved`, `sandbox_provisioning_started`, `sandbox_provisioning_completed`, `workspace_materialization_started`, `workspace_materialization_completed`, `workspace_materialization_failed`. These events should be versioned in API docs and clearly marked as Minerva-specific.

## 5. Export serializer strategy

### 5.1 Export architecture

Create a dedicated exporter under `services/orchestrator/src/session/session-export.service.ts` with helpers under `src/session/export/`: `session-jsonl-serializer.ts`, `session-export-metadata.ts`, `session-export-types.ts`, and `session-export-fixtures.ts`.

### 5.2 Source of truth

Exports must be generated from `sessions`, `session_entries`, and selected `runs` metadata only when needed for compatibility metadata. Do not generate exports from SSE logs.

### 5.3 Serialization rules

1. load session header row
2. load durable entry path or complete exportable graph in `sequence` order
3. map each durable row to a pi-shaped JSONL line
4. preserve `id` and `parentId` semantics
5. emit hosted-only metadata into a sidecar file, not into the pi JSONL line unless unavoidable
6. include compatibility notes when a hosted payload cannot map exactly to pi semantics

### 5.4 Output bundle

Recommended HTTP export response: `session.jsonl`, `metadata.json`, and optional `attachments/` for oversized tool outputs in later slices.
Recommended metadata fields: `exportVersion`, `minervaVersion`, `sessionId`, `exportedAt`, `compatibilityNotes`, `entryCount`, `hasHiddenBranchMetadata`.

### 5.5 Test strategy

Add golden fixtures under `services/orchestrator/tests/fixtures/session-exports/*.jsonl` and `services/orchestrator/tests/fixtures/session-exports/*.metadata.json`.
Add tests for: single linear conversation, tool result conversation, model/thinking change entries, hidden branch metadata retained in export ids/parents, and replay event noise excluded from export.

## 6. Phased implementation slices

Each slice should ship independently and keep the system working.

### Slice 1: Durable repository foundation
Outcome: Prisma schema widened for session-first persistence and repository implementations exist beside current in-memory lifecycle paths.
Files expected: `services/orchestrator/prisma/schema.prisma`, `services/orchestrator/prisma/migrations/*`, `services/orchestrator/src/repo/*.ts`, tests for repository append/replay behavior.
Done when: session, entry, run, binding, and replay repositories work against Postgres, and no runtime execution path depends on in-memory-only persistence for durable records.

### Slice 2: Session command and runtime scaffolding
Outcome: session module exists and `RunExecutionService` delegates to session-aware services for creation and execution setup.
Files expected: `services/orchestrator/src/session/*`, updates to `services/orchestrator/src/runtime/run-execution.service.ts`, updates to `services/orchestrator/src/runtime/runtime.module.ts`.
Done when: a run can be created with a durable `session_id`, and context reconstruction happens from stored entries even if only a linear path is used initially.

### Slice 3: Sandbox binding and workspace materialization
Outcome: stable sandbox/workspace bindings exist and runtime resources are materialized inside the workspace runtime root.
Files expected: `services/orchestrator/src/sandbox/sandbox-binding.service.ts`, `services/orchestrator/src/sandbox/workspace-materializer.service.ts`, `services/orchestrator/src/resources/*`, updated `services/orchestrator/src/sandbox/adapter.ts`.
Done when: runs no longer depend on orchestrator-host pack paths during execution, and repeated runs for the same owner+agent reuse durable binding metadata.

### Slice 4: Durable SSE replay and session-aware APIs
Outcome: SSE replay comes from Postgres-backed events and session endpoints exist in parallel with run compatibility endpoints.
Files expected: `services/orchestrator/src/sse/*`, `services/orchestrator/src/sessions/*`, `docs/api/endpoints.md`, `docs/api/sse-schema.md`.
Done when: reconnect after process restart can replay terminal and durable-derived events, and all new events include `session_id`.

### Slice 5: Exporter and compatibility hardening
Outcome: pi-shaped session export works from Postgres durable history and golden export fixtures protect compatibility.
Files expected: `services/orchestrator/src/session/export/*`, `services/orchestrator/tests/fixtures/session-exports/*`, `docs/plans/minerva-qqaa/*`, and any finalized canonical follow-up docs promoted after approval.
Done when: exported JSONL reflects durable entries rather than final message snapshots, and compatibility notes document any deliberate divergence from pi.

## 7. Suggested follow-up child beans

These should be created after approval to execute:
1. `Implement minerva-qqaa Postgres session repositories and migrations`
2. `Introduce minerva-qqaa session runtime module and command flow`
3. `Add minerva-qqaa sandbox binding and workspace materialization services`
4. `Add minerva-qqaa session-aware HTTP/SSE contracts`
5. `Implement minerva-qqaa pi-shaped session export serializer`

## 8. Exit criteria for minerva-qqaa planning

The planning portion of `minerva-qqaa` is complete when current vs target runtime gaps are documented; Postgres schema and repository boundaries are concrete; runtime adapter boundaries are concrete; sandbox binding and materialization flow is concrete; HTTP/SSE and export contracts are concrete enough to build against; and implementation slices are small enough to become child beans without re-planning.
