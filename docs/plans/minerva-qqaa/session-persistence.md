# Postgres-backed session persistence proposal

## Purpose

Define the durable data model Minerva could use to emulate pi coding agent session behavior while operating as a hosted service. This is proposal material, not ratified canonical architecture.

## References

- [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)
- [`docs/research/pi-agent-core/sessions.md`](../../research/pi-agent-core/sessions.md)
- [`services/orchestrator/src/types/run.ts`](../../../services/orchestrator/src/types/run.ts)
- [`services/orchestrator/src/services/run-manager.ts`](../../../services/orchestrator/src/services/run-manager.ts)

## Design goals

- preserve pi-like session and entry semantics where practical
- keep durable writes append-oriented
- avoid persisting every streaming delta
- support hosted replay, auditability, and operational queries
- preserve hidden branch-capable internals for future UX evolution
- support pi-shaped session export without forcing JSONL as the primary store

## Durability boundary

Minerva should mirror pi's practical durability boundary:

- stream assistant deltas and tool progress live over SSE
- persist finalized records when a durable session boundary is reached

Durable boundaries for v1:

- session created
- user prompt accepted into a session
- assistant message finalized
- tool result finalized
- model change recorded
- thinking level change recorded
- label metadata change recorded
- branch/compaction/custom entry recorded
- run attempt lifecycle transitions recorded

Do not persist every token delta or every stdout chunk as canonical session history.

## Logical model

### 1. Sessions

Represents the long-lived hosted equivalent of a pi session file.

Suggested fields:

- `session_id` (ULID/UUID)
- `tenant_id`
- `owner_id`
- `agent_id` or `agent_pack_id`
- `workspace_key`
- `sandbox_binding_key`
- `status`
- `current_leaf_entry_id`
- `display_name`
- `created_at`
- `updated_at`
- `last_active_at`
- `export_version`

### 2. Session entries

Represents the append-only tree of durable records analogous to pi JSONL entries.

Suggested fields:

- `entry_id`
- `session_id`
- `parent_entry_id`
- `entry_type`
- `created_at`
- `author_kind` (`system`, `user`, `assistant`, `tool`, `runtime`, `extension`)
- `payload_json`
- `context_inclusion` boolean
- `run_id` nullable
- `sequence_in_session` monotonic bigint

Entry types should cover at least:

- `message`
- `model_change`
- `thinking_level_change`
- `compaction`
- `branch_summary`
- `custom`
- `custom_message`
- `label`
- `session_info`

### 3. Runs

Represents execution attempts against a durable session.

Suggested fields:

- `run_id`
- `session_id`
- `tenant_id`
- `owner_id`
- `state`
- `request_kind` (`prompt`, `steer`, `follow_up`, `resume`, internal maintenance)
- `requested_entry_id` nullable
- `created_at`
- `started_at`
- `completed_at`
- `max_duration_ms`
- `error_code` nullable
- `error_message` nullable
- `sandbox_id` nullable

### 4. Event log

Represents replayable runtime events for SSE and observability.

Suggested fields:

- `run_id`
- `session_id`
- `seq`
- `event_type`
- `emitted_at`
- `payload_json`
- `is_terminal`
- `durability_class` (`transient_replayable`, `derived_from_entry`, `run_lifecycle`)

This table is not the source of truth for session context. It is the source of truth for replayable hosted event delivery.

### 5. Session projections

Use read-optimized projections for common queries instead of forcing all reads through entry graph reconstruction.

Examples:

- latest session summary per owner/agent/workspace
- latest model/thinking settings per session
- labels projection by target entry
- latest active branch metadata
- resumable run/session lookup by owner and workspace

## Mapping pi entry semantics to Postgres

| Pi concept | Minerva durable form |
|---|---|
| Session header | `sessions` row |
| JSONL message entry | `session_entries` row with `entry_type=message` |
| Tree via `id`/`parentId` | `entry_id` and `parent_entry_id` |
| Current leaf | `sessions.current_leaf_entry_id` |
| Label entry | append-only label entry + optional labels projection |
| Session info | append-only info entry + optional session display_name projection |
| Custom entry | append-only `entry_type=custom` payload |
| Compaction entry | append-only summary entry linked to kept entry |
| Branch summary | append-only summary entry with source linkage |

## Context reconstruction rules

To build runtime context for a session:

1. load the current leaf entry for the session
2. walk parent links back to the root
3. reverse into chronological order
4. apply branch-summary and compaction rules the same way pi conceptually does
5. derive active model and thinking settings from the latest applicable entries on the selected path
6. exclude entries marked non-contextual

The database should not store a mutable flattened transcript as the canonical record. It may store one as a cache or projection.

## Recommended write strategy

Use transactional append behavior:

- write finalized session entry rows inside a single DB transaction
- update `sessions.current_leaf_entry_id` in that same transaction
- optionally append derived run/event rows in the same transaction when they share a durable boundary

Examples:

- when an assistant message finishes, append the assistant `message` entry and any finalized tool result entries, then advance the session leaf
- when a run completes, record terminal run state and append any missing durable entries, but do not backfill streaming deltas into session history

## Replay and export model

Minerva should support two outputs from the same durable source:

### Hosted replay

Use the `run_events` log to replay SSE after disconnects or worker restarts.

### Pi-shaped export

Build JSONL exports from `sessions` + `session_entries` by:

1. emitting a synthetic session header line
2. serializing each durable entry into pi-like JSONL form
3. preserving `entry_id` and `parent_entry_id` semantics
4. including enough metadata to support pi-style tree inspection where practical

Exports are compatibility artifacts, not the primary write path.

## Operational benefits

This model allows:

- tenant-aware queries without parsing session files
- selective retention policies for events vs durable history
- resumable hosted sessions across process restarts
- auditability of both session history and run attempts
- future support for branching UX without changing the canonical history format

## Deferred items

These should be modeled but may remain inactive in v1:

- exposed user branching UI
- destructive compaction cleanup
- workspace snapshot blobs
- extension-managed custom state beyond simple payload records
- cross-session fork lineage beyond basic parent references

## Layer 2 planning outputs needed

- exact table schema and indexes
- transaction boundaries for each runtime operation
- retention policy for replay events
- migration plan from `InMemoryRunRepository` to Postgres repositories
- export serializer contract and golden test fixtures
