# API Documentation

## Overview

Minerva Orchestrator v0 API provides HTTP endpoints for managing agent runs and SSE streaming for real-time event delivery.

## Base URL

```
http://localhost:3000/api/v0
```

## Authentication

See [Authentication](./authentication.md) for details.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/runs` | POST | Create a new run |
| `/runs/:runId` | GET | Get run status and metadata |
| `/runs/:runId/cancel` | POST | Cancel a running or queued run |
| `/runs/:runId/stream` | GET | SSE stream for run events |

## Quick Start

### Create a Run

```bash
curl -X POST http://localhost:3000/api/v0/runs \
  -H "Content-Type: application/json" \
  -d '{
    "agentPackId": "default",
    "prompt": "Hello, world!"
  }'
```

### Stream Events

```bash
curl -N http://localhost:3000/api/v0/runs/{runId}/stream \
  -H "Accept: text/event-stream"
```

## Documentation Sections

- [Endpoints Reference](./endpoints.md) - Detailed endpoint documentation
- [SSE Schema](./sse-schema.md) - Event types and payloads
- [Authentication](./authentication.md) - Authentication methods

## Error Handling

All errors follow the standard HTTP status codes:

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Authentication required |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Invalid state transition |
| 422 | Unprocessable Entity - Validation error |
| 500 | Internal Server Error |

Error responses include a JSON body:

```json
{
  "error": "RUN_NOT_FOUND",
  "message": "Run with ID 'run-123' not found",
  "code": "NOT_FOUND"
}
```
