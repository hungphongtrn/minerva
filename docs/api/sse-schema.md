# SSE Event Schema

## Overview

Server-Sent Events (SSE) provide real-time streaming of run lifecycle events. All events follow a consistent envelope structure with monotonically increasing sequence numbers per run.

## Event Envelope

All SSE events share this envelope structure:

```typescript
interface SSEEventEnvelope<TPayload> {
  type: SSEEventType;      // Event type discriminator
  run_id: string;          // Run identifier (ULID)
  ts: string;              // ISO 8601 UTC timestamp
  seq: number;             // Monotonically increasing sequence number
  payload: TPayload;       // Event-specific payload
}
```

### Sequence Numbers

- **Monotonic**: Each event increments `seq` by 1 within a run
- **Per-run isolation**: Different runs have independent sequence counters
- **Starting at 1**: First event for each run has `seq: 1`
- **Replay support**: Use `Last-Event-ID` header to resume from specific sequence

### Timestamps

All timestamps are in ISO 8601 format with millisecond precision:

```
2024-01-15T10:30:00.123Z
```

## Event Types

### Orchestrator Lifecycle Events

#### `run_queued`

Emitted when a run is added to the queue.

```json
{
  "type": "run_queued",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:00.000Z",
  "seq": 1,
  "payload": {
    "queue_position": 0,
    "estimated_start": "2024-01-15T10:30:30.000Z"
  }
}
```

**Payload Fields:**
- `queue_position` (number): Position in FIFO queue (0-indexed)
- `estimated_start` (string, optional): ISO 8601 timestamp of estimated start time

---

#### `run_started`

Emitted when the run transitions to RUNNING state.

```json
{
  "type": "run_started",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:05.000Z",
  "seq": 2,
  "payload": {
    "started_at": "2024-01-15T10:30:05.000Z",
    "sandbox_id": "ws_user-123_..."
  }
}
```

**Payload Fields:**
- `started_at` (string): When the run started executing
- `sandbox_id` (string, optional): Workspace/sandbox identifier

---

#### `run_completed`

Terminal event emitted when run finishes successfully.

```json
{
  "type": "run_completed",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:35:00.000Z",
  "seq": 100,
  "payload": {
    "completed_at": "2024-01-15T10:35:00.000Z",
    "duration_ms": 300000
  }
}
```

**Payload Fields:**
- `completed_at` (string): When the run completed
- `duration_ms` (number): Total duration in milliseconds

---

#### `run_failed`

Terminal event emitted when run encounters an error.

```json
{
  "type": "run_failed",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:32:00.000Z",
  "seq": 50,
  "payload": {
    "failed_at": "2024-01-15T10:32:00.000Z",
    "error": "Sandbox creation timeout",
    "error_code": "TIMEOUT"
  }
}
```

**Payload Fields:**
- `failed_at` (string): When the failure occurred
- `error` (string): Error message
- `error_code` (string, optional): Machine-readable error code

---

#### `run_cancelled`

Terminal event emitted when run is cancelled.

```json
{
  "type": "run_cancelled",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:31:00.000Z",
  "seq": 30,
  "payload": {
    "cancelled_at": "2024-01-15T10:31:00.000Z",
    "reason": "User requested cancellation"
  }
}
```

**Payload Fields:**
- `cancelled_at` (string): When the run was cancelled
- `reason` (string, optional): Cancellation reason

---

#### `run_timed_out`

Terminal event emitted when run exceeds maxDurationMs.

```json
{
  "type": "run_timed_out",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:40:00.000Z",
  "seq": 200,
  "payload": {
    "timed_out_at": "2024-01-15T10:40:00.000Z",
    "timeout_duration_ms": 600000
  }
}
```

**Payload Fields:**
- `timed_out_at` (string): When the timeout occurred
- `timeout_duration_ms` (number): Configured timeout duration

---

### Stream Connection Events

#### `stream_connected`

Emitted when a client connects to the SSE stream.

```json
{
  "type": "stream_connected",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:00.500Z",
  "seq": 0,
  "payload": {
    "run_state": "queued",
    "replay_from": null
  }
}
```

**Payload Fields:**
- `run_state` (string): Current state of the run
- `replay_from` (number | null): Sequence number replay resumed from, or null for new connection

---

### Agent Lifecycle Events (pi-agent-core)

#### `agent_start`

Emitted when the agent loop begins.

```json
{
  "type": "agent_start",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:06.000Z",
  "seq": 3,
  "payload": {}
}
```

---

#### `agent_end`

Emitted when the agent loop completes.

```json
{
  "type": "agent_end",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:34:59.000Z",
  "seq": 99,
  "payload": {
    "messages": [...]
  }
}
```

**Payload Fields:**
- `messages` (array): Final message history

---

### Turn Lifecycle Events (pi-agent-core)

#### `turn_start`

Emitted at the start of each agent turn.

```json
{
  "type": "turn_start",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:07.000Z",
  "seq": 4,
  "payload": {
    "turn_number": 1
  }
}
```

**Payload Fields:**
- `turn_number` (number): Turn index (1-based)

---

#### `turn_end`

Emitted at the end of each agent turn.

```json
{
  "type": "turn_end",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:32:00.000Z",
  "seq": 50,
  "payload": {
    "turn_number": 1,
    "message": {...},
    "tool_results": [...]
  }
}
```

---

### Message Lifecycle Events (pi-agent-core)

#### `message_start`

Emitted when the LLM starts generating a message.

```json
{
  "type": "message_start",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:08.000Z",
  "seq": 5,
  "payload": {
    "message": {...}
  }
}
```

---

#### `message_update`

Emitted for streaming message updates (tokens, tool calls).

```json
{
  "type": "message_update",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:09.000Z",
  "seq": 6,
  "payload": {
    "message": {...},
    "delta_type": "text_delta",
    "delta": "Hello"
  }
}
```

**Delta Types:**
- `text_delta`: Text token update
- `thinking_delta`: Reasoning/thinking update
- `toolcall_start`: New tool call initiated
- `toolcall_delta`: Tool call arguments streaming

---

#### `message_end`

Emitted when message generation completes.

```json
{
  "type": "message_end",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:15.000Z",
  "seq": 20,
  "payload": {
    "message": {...}
  }
}
```

---

### Tool Execution Events (pi-agent-core)

#### `tool_execution_start`

Emitted when a tool begins execution.

```json
{
  "type": "tool_execution_start",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:16.000Z",
  "seq": 21,
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "bash",
    "args": {
      "command": "ls -la"
    }
  }
}
```

**Payload Fields:**
- `tool_call_id` (string): Unique tool call identifier
- `tool_name` (string): Name of the tool
- `args` (object): Tool arguments

---

#### `tool_execution_update`

Emitted during tool execution (stdout/stderr streaming).

```json
{
  "type": "tool_execution_update",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:17.000Z",
  "seq": 22,
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "bash",
    "partial_result": {
      "type": "stdout",
      "data": "total 128\ndrwxr-xr-x"
    }
  }
}
```

**Partial Result Types:**
- `stdout`: Standard output chunk
- `stderr`: Standard error chunk
- `progress`: Progress update (for long-running operations)

---

#### `tool_execution_end`

Emitted when tool execution completes.

```json
{
  "type": "tool_execution_end",
  "run_id": "run_01HV8F...",
  "ts": "2024-01-15T10:30:18.000Z",
  "seq": 23,
  "payload": {
    "tool_call_id": "call_abc123",
    "tool_name": "bash",
    "result": {...},
    "is_error": false,
    "duration_ms": 1500
  }
}
```

**Payload Fields:**
- `result` (any): Tool result data
- `is_error` (boolean): Whether the tool returned an error
- `duration_ms` (number): Execution duration

---

## Event Categories

Events are categorized by prefix:

| Category | Prefix | Description |
|----------|--------|-------------|
| Orchestrator | `run_` | Run lifecycle management |
| Stream | `stream_` | Connection events |
| Agent | `agent_` | Agent loop lifecycle |
| Turn | `turn_` | Turn-based execution |
| Message | `message_` | Message streaming |
| Tool | `tool_execution_` | Tool execution |

## Terminal Events

The following events indicate run completion and trigger stream closure:

- `run_completed` - Success
- `run_failed` - Error occurred
- `run_cancelled` - Cancelled by user/system
- `run_timed_out` - Timeout exceeded

## Event Ordering Guarantees

1. **Monotonic seq**: `seq` always increases by 1 (no gaps, no duplicates)
2. **Chronological ts**: Timestamps reflect event emission order
3. **Causal order**: Events within a logical operation follow expected sequence (e.g., `tool_execution_start` before `tool_execution_end`)
4. **Per-run isolation**: Events from different runs are not interleaved in a single stream

## Connection Lifecycle

```
1. Client connects → stream_connected event emitted
2. Run events stream in seq order
3. Terminal event emitted
4. Server closes connection
```

## Reconnection and Replay

To resume a stream from a specific event:

```http
GET /api/v0/runs/{runId}/stream
Last-Event-ID: 42
```

The server will:
1. Emit `stream_connected` with `replay_from: 42`
2. Replay events from seq 43 onwards
3. Continue with new events

**Note:** Replay buffer may be limited (e.g., last 100 events). Events outside the buffer window will not be replayed.
