# API Endpoints Reference

## POST /runs

Create a new agent run.

### Request

```http
POST /api/v0/runs
Content-Type: application/json

{
  "userId": "string",          // Optional: Defaults to "anonymous"
  "agentPackId": "string",     // Required: Agent pack to use
  "prompt": "string",          // Required: User prompt
  "maxDurationMs": number      // Optional: Max duration in milliseconds (default: 10min, max: 1hr)
}
```

### Response

**201 Created**

```json
{
  "runId": "run_01HV8F...",
  "state": "queued",
  "createdAt": "2024-01-15T10:30:00.000Z",
  "queuePosition": 0,
  "userId": "user-123"
}
```

**400 Bad Request**

```json
{
  "error": "VALIDATION_ERROR",
  "message": "prompt is required"
}
```

### Example

```bash
curl -X POST http://localhost:3000/api/v0/runs \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-123",
    "agentPackId": "default",
    "prompt": "Write a hello world program in Python"
  }'
```

---

## GET /runs/:runId

Get run status and metadata.

### Request

```http
GET /api/v0/runs/{runId}
```

### Response

**200 OK**

```json
{
  "runId": "run_01HV8F...",
  "userId": "user-123",
  "state": "running",          // queued | leased | running | completed | failed | cancelled | timed_out
  "createdAt": "2024-01-15T10:30:00.000Z",
  "startedAt": "2024-01-15T10:30:05.000Z",
  "completedAt": null,
  "queuePosition": null,
  "error": null,
  "durationMs": 15000
}
```

**404 Not Found**

```json
{
  "error": "RUN_NOT_FOUND",
  "message": "Run 'run_01HV8F...' not found"
}
```

### Example

```bash
curl http://localhost:3000/api/v0/runs/run_01HV8F...
```

---

## POST /runs/:runId/cancel

Cancel a running or queued run.

### Request

```http
POST /api/v0/runs/{runId}/cancel
Content-Type: application/json

{
  "reason": "string"  // Optional: Cancellation reason
}
```

### Response

**200 OK**

```json
{
  "runId": "run_01HV8F...",
  "state": "cancelled",
  "cancelledAt": "2024-01-15T10:35:00.000Z",
  "reason": "User requested cancellation"
}
```

**409 Conflict** - Run already in terminal state

```json
{
  "error": "INVALID_STATE_TRANSITION",
  "message": "Cannot cancel run in state 'completed'"
}
```

**404 Not Found**

```json
{
  "error": "RUN_NOT_FOUND",
  "message": "Run 'run_01HV8F...' not found"
}
```

### Example

```bash
curl -X POST http://localhost:3000/api/v0/runs/run_01HV8F.../cancel \
  -H "Content-Type: application/json" \
  -d '{"reason": "Changed my mind"}'
```

---

## GET /runs/:runId/stream

SSE stream for run events. Provides real-time updates on run lifecycle, agent execution, and tool results.

### Request

```http
GET /api/v0/runs/{runId}/stream
Accept: text/event-stream
replayFrom=42                     // Optional query param alternative
Last-Event-ID: 42  // Optional: Replay from sequence number
```

### Response

**200 OK** - Server-Sent Events stream

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: run_queued
data: {"type":"run_queued","run_id":"run_01HV8F...","ts":"2024-01-15T10:30:00.000Z","seq":1,"payload":{"queue_position":0}}

event: run_started
data: {"type":"run_started","run_id":"run_01HV8F...","ts":"2024-01-15T10:30:05.000Z","seq":2,"payload":{"started_at":"2024-01-15T10:30:05.000Z"}}

event: agent_start
data: {"type":"agent_start","run_id":"run_01HV8F...","ts":"2024-01-15T10:30:06.000Z","seq":3,"payload":{}}

...

event: run_completed
data: {"type":"run_completed","run_id":"run_01HV8F...","ts":"2024-01-15T10:35:00.000Z","seq":100,"payload":{"completed_at":"2024-01-15T10:35:00.000Z","duration_ms":300000}}
```

**404 Not Found**

```json
{
  "error": "RUN_NOT_FOUND"
}
```

### Event Stream Behavior

- **Connection**: HTTP connection remains open until run completes or client disconnects
- **Reconnection**: Clients can reconnect with `Last-Event-ID` header to resume from last received event
- **Heartbeat**: Server sends periodic comments (`:keepalive`) to keep connection alive
- **Termination**: Stream closes after terminal event (`run_completed`, `run_failed`, `run_cancelled`, `run_timed_out`)

### Example

```bash
curl -N http://localhost:3000/api/v0/runs/run_01HV8F.../stream \
  -H "Accept: text/event-stream"
```

**JavaScript EventSource Example:**

```javascript
const eventSource = new EventSource('/api/v0/runs/run_01HV8F.../stream');

eventSource.addEventListener('run_queued', (event) => {
  const data = JSON.parse(event.data);
  console.log('Run queued at position:', data.payload.queue_position);
});

eventSource.addEventListener('run_started', (event) => {
  console.log('Run started!');
});

eventSource.addEventListener('run_completed', (event) => {
  console.log('Run completed!');
  eventSource.close();
});

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
};
```

---

## Run States

| State | Description |
|-------|-------------|
| `queued` | Run is waiting in the queue |
| `leased` | Run has acquired a lease and is preparing |
| `running` | Agent loop is actively executing |
| `completed` | Run finished successfully |
| `failed` | Run encountered an error |
| `cancelled` | Run was cancelled by user or system |
| `timed_out` | Run exceeded maxDurationMs |

### State Transitions

```
queued → leased → running → completed
              ↓
           failed
              ↓
          cancelled
              ↓
          timed_out

queued → cancelled (direct cancellation)
leased → cancelled (cancellation during setup)
```
