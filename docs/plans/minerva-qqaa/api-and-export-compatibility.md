# HTTP, SSE, and export compatibility proposal

## Purpose

Define the externally visible contracts Minerva could evolve toward so hosted sessions feel pi-like without exposing unsafe or local-only behaviors to consumers. This is proposal material, not ratified canonical architecture.

## References

- [`docs/api/sse-schema.md`](../../api/sse-schema.md)
- [`docs/api/endpoints.md`](../../api/endpoints.md)
- [`docs/specs/event-streaming.md`](../../specs/event-streaming.md)
- [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)
- [`docs/research/pi-agent-core/sessions.md`](../../research/pi-agent-core/sessions.md)

## Contract direction

Minerva should present pi-like runtime behavior through hosted HTTP/SSE APIs rather than exposing raw local SDK assumptions.

This means:

- preserve event taxonomy as closely as practical
- make session identity explicit in addition to run identity
- keep consumer-facing APIs safe by blocking unsupported slash-command behavior
- support replay and resume without requiring clients to understand internal persistence details
- provide session export in a pi-shaped artifact for interoperability

## HTTP model changes

### Current shape

The current API is run-centric:

- `POST /runs`
- `GET /runs/:runId`
- `POST /runs/:runId/cancel`
- `GET /runs/:runId/stream`

### Target shape

Keep run endpoints for execution control, but make them subordinate to durable sessions.

Recommended additions for planning:

- `POST /sessions` to create or resolve a hosted session binding
- `GET /sessions/:sessionId` for session metadata and resumability
- `POST /sessions/:sessionId/runs` for prompt/follow-up execution
- `GET /sessions/:sessionId/stream` for session-scoped event streaming or multiplexed replay
- `GET /sessions/:sessionId/export` for pi-shaped export

A compatible migration path can preserve current run endpoints by treating `POST /runs` as shorthand for creating a transient-or-default session-backed run.

## SSE envelope updates

Retain the current envelope shape and extend it rather than replacing it.

Recommended envelope:

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

### Required improvements

- `session_id` added to every event
- `seq` sourced from durable event storage for replayable streams
- event payloads should distinguish transient deltas from finalized records where needed
- terminal events should always be reproducible from durable run/event data

## Event taxonomy guidance

### Keep nearly unchanged

These pi-derived lifecycle events should stay close to the reference:

- `agent_start`
- `agent_end`
- `turn_start`
- `turn_end`
- `message_start`
- `message_update`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`

### Hosted orchestration extensions

These remain Minerva-specific and should stay versioned/documented as hosted runtime events:

- `run_queued`
- `run_started`
- `run_completed`
- `run_failed`
- `run_cancelled`
- `run_timed_out`
- optional future events such as `session_resumed`, `sandbox_provisioning`, `workspace_materialized`

## Replay behavior

Replay should be reliable after client disconnects and service restarts.

Recommended behavior:

1. client connects with optional `Last-Event-ID`
2. server resolves replay window from durable `run_events`
3. server replays all later events in order
4. server continues streaming live events from the active run
5. server closes only after a terminal event or client disconnect

Replay gaps should produce an explicit error response or a documented restart-from-zero policy, not silent partial history.

## Consumer-safe behavior constraints

Because Minerva serves consumer-facing products, the API should not expose all local pi command surfaces.

### Slash and prompt commands

- consumer APIs should reject slash commands and extension commands in raw prompts
- developer or internal APIs may enable a richer command envelope later
- prompt templates can still exist internally if expanded before user-facing execution begins

### Hosted safety expectations

- do not expose local filesystem paths from the orchestrator host
- do not expose raw sandbox infrastructure internals unless needed for debugging
- normalize infrastructure failures into stable API error codes

## Export compatibility

Minerva should support exporting a hosted session into a pi-shaped artifact when practical.

### Export contents

Recommended export bundle contents:

- a primary JSONL session artifact shaped like pi session history
- export metadata file describing Minerva version, export timestamp, and known compatibility gaps
- optional auxiliary files for large tool outputs or attachment references

### Compatibility goals

Exports should preserve:

- session header semantics
- durable message ordering
- `entry_id` and `parent_entry_id` tree semantics
- model/thinking changes
- labels, compaction summaries, and branch summaries where stored

Exports do not need to preserve:

- every live SSE token delta
- every transient sandbox lifecycle event
- hosted-only operational metadata that pi would not understand

## Suggested versioning approach

Use explicit versions for hosted API and export contracts.

- HTTP/SSE contract version via `/api/v1` or headers
- export manifest version in metadata
- compatibility notes recorded when a hosted field cannot map exactly to pi JSONL

## Layer 2 planning outputs needed

- exact session and run endpoint request/response bodies
- durable replay rules and retention limits
- error code catalog for hosted runtime failures
- export schema fixtures and golden tests
- migration strategy from current run-only endpoints to session-aware APIs
