# ZeroClaw Gateway API Reference

## Overview

The ZeroClaw Gateway provides a secure HTTP API for interacting with the ZeroClaw autonomous agent runtime. It supports multiple integration patterns including direct webhook messaging, channel integrations (WhatsApp, Telegram, Discord, etc.), and real-time streaming via WebSocket.

**Base URL**: `http://localhost:3000` (default)

**Protocol**: HTTP/1.1

**Content-Type**: `application/json`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ZeroClaw Gateway                         │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Health  │  │  Pair    │  │ Webhook  │  │ Metrics  │   │
│  │   /health│  │  /pair   │  │  /webhook│  │ /metrics │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │             │             │          │
│       └─────────────┴─────────────┴─────────────┘          │
│                       │                                     │
│              ┌────────▼────────┐                           │
│              │  Rate Limiter   │                           │
│              │  (Sliding Win)  │                           │
│              └────────┬────────┘                           │
│                       │                                     │
│              ┌────────▼────────┐                           │
│              │  Auth Layer     │                           │
│              │  (Bearer/Secret)│                           │
│              └────────┬────────┘                           │
│                       │                                     │
│              ┌────────▼────────┐                           │
│              │   Agent Core    │                           │
│              │  (ZeroClaw LLM) │                           │
│              └─────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Endpoints

### 1. Health Check

**Purpose**: Verify gateway availability and runtime status

**Endpoint**: `GET /health`

**Authentication**: None (public)

**Response** (200 OK):

```json
{
  "status": "ok",
  "paired": true,
  "runtime": {
    "pid": 12345,
    "updated_at": "2026-03-06T12:00:00Z",
    "uptime_seconds": 3600,
    "components": {
      "gateway": {
        "status": "ok",
        "version": "0.1.0"
      }
    }
  }
}
```

**Example Request**:

```bash
curl http://localhost:3000/health
```

---

### 2. Metrics (Prometheus)

**Purpose**: Export runtime metrics in Prometheus format

**Endpoint**: `GET /metrics`

**Authentication**: None (public)

**Content-Type**: `text/plain; version=0.0.4; charset=utf-8`

**Response**: Prometheus exposition format

```
# HELP zeroclaw_requests_total Total number of requests
# TYPE zeroclaw_requests_total counter
zeroclaw_requests_total{endpoint="/webhook"} 42

# HELP zeroclaw_request_duration_seconds Request duration
# TYPE zeroclaw_request_duration_seconds histogram
zeroclaw_request_duration_seconds_bucket{le="0.1"} 38
...
```

**Prerequisites**: 
- Configure `[observability] backend = "prometheus"` in `config.toml`

**Example Request**:

```bash
curl http://localhost:3000/metrics
```

---

### 3. Client Pairing

**Purpose**: Exchange one-time pairing code for bearer token

**Endpoint**: `POST /pair`

**Authentication**: 
- `X-Pairing-Code` header (displayed at gateway startup)
- Rate limited (configurable)

**Request Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `X-Pairing-Code` | Yes | 6-digit code from startup logs |

**Response** (200 OK):

```json
{
  "paired": true,
  "persisted": true,
  "token": "zeroclaw_abc123xyz789...",
  "message": "Save this token — use it as Authorization: Bearer <token>"
}
```

**Error Responses**:
- `403 Forbidden`: Invalid or expired pairing code
- `429 Too Many Requests`: Rate limit exceeded

**Example Request**:

```bash
curl -X POST http://localhost:3000/pair \
  -H "X-Pairing-Code: 732047"
```

---

### 4. Main Webhook

**Purpose**: Send messages to the agent and receive responses

**Endpoint**: `POST /webhook`

**Authentication**:
- `Authorization: Bearer <token>` (if pairing enabled)
- `X-Webhook-Secret: <hash>` (optional additional layer)

**Rate Limiting**: Configurable (default: 100/minute)

**Request Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `Authorization` | If pairing enabled | `Bearer <token>` |
| `X-Webhook-Secret` | If configured | SHA-256 hash of secret |
| `X-Idempotency-Key` | No | UUID for deduplication |

**Request Body**:

```json
{
  "message": "What is the weather in Tokyo?"
}
```

**Response** (200 OK):

```json
{
  "response": "The current weather in Tokyo is...",
  "model": "anthropic/claude-sonnet-4",
  "tokens": {
    "input": 15,
    "output": 142
  }
}
```

**Duplicate Response** (200 OK, idempotent):

```json
{
  "status": "duplicate",
  "idempotent": true,
  "message": "Request already processed for this idempotency key",
  "original_response": "..."
}
```

**Error Responses**:
- `400 Bad Request`: Invalid JSON or missing message field
- `401 Unauthorized`: Missing/invalid bearer token
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: LLM request failed

**Example Request**:

```bash
# With pairing token
curl -X POST http://localhost:3000/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer zeroclaw_abc123..." \
  -d '{"message": "Hello, what can you do?"}'

# With webhook secret (additional auth layer)
curl -X POST http://localhost:3000/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer zeroclaw_abc123..." \
  -H "X-Webhook-Secret: sha256_hash_here" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -d '{"message": "Process this task"}'
```

---

## Channel Integration Endpoints

### 5. WhatsApp Verification

**Purpose**: Meta WhatsApp Cloud API webhook verification

**Endpoint**: `GET /whatsapp`

**Authentication**: None (verification handshake)

**Query Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `hub.mode` | Yes | Must be `"subscribe"` |
| `hub.verify_token` | Yes | Must match config |
| `hub.challenge` | Yes | String to echo back |

**Response** (200 OK): Echoes `hub.challenge` value

**Error Response** (403): Forbidden (token mismatch)

**Example Request**:

```bash
curl "http://localhost:3000/whatsapp?\
hub.mode=subscribe&\
hub.verify_token=YOUR_VERIFY_TOKEN&\
hub.challenge=CHALLENGE_STRING"
```

---

### 6. WhatsApp Messages

**Purpose**: Receive incoming WhatsApp messages

**Endpoint**: `POST /whatsapp`

**Authentication**: 
- `X-Hub-Signature-256` header (if `app_secret` configured)

**Request Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Hub-Signature-256` | If app_secret set | `sha256=<signature>` |

**Request Body**: Meta WhatsApp Cloud API payload

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "1234567890",
          "id": "wamid.123...",
          "timestamp": "1234567890",
          "text": {
            "body": "Hello from WhatsApp"
          },
          "type": "text"
        }]
      }
    }]
  }]
}
```

**Response** (200 OK):

```json
{
  "status": "ok"
}
```

**Processing Flow**:

1. Validate HMAC-SHA256 signature (if configured)
2. Parse message from payload
3. Auto-save to memory (if enabled)
4. Send to LLM for processing
5. Send reply via WhatsApp Cloud API

**Configuration Required**:

```toml
[channels_config.whatsapp]
access_token = "EAABx..."
phone_number_id = "123456789012345"
verify_token = "my-secret-verify-token"
app_secret = "app_secret_for_signatures"
allowed_numbers = ["+1234567890"]
```

---

### 7. Linq Messages (iMessage/RCS/SMS)

**Purpose**: Receive messages via Linq bridge

**Endpoint**: `POST /linq`

**Authentication**: 
- Signature headers (if `signing_secret` configured)

**Request Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Webhook-Timestamp` | If signing_secret | Unix timestamp |
| `X-Webhook-Signature` | If signing_secret | HMAC signature |

**Request Body**: Linq webhook payload

```json
{
  "from": "+1234567890",
  "to": "+0987654321",
  "body": "Hello via Linq",
  "timestamp": "2026-03-06T12:00:00Z",
  "channel": "imessage"
}
```

**Response** (200 OK):

```json
{
  "status": "ok"
}
```

**Configuration Required**:

```toml
[channels_config.linq]
webhook_url = "https://your-domain/linq"
signing_secret = "your_signing_secret"
allowed_senders = ["+1234567890"]
```

---

### 8. Nextcloud Talk

**Purpose**: Receive messages from Nextcloud Talk bots

**Endpoint**: `POST /nextcloud-talk`

**Authentication**:
- HMAC signature (if `webhook_secret` configured)

**Request Headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Nextcloud-Talk-Random` | If webhook_secret | Random string |
| `X-Nextcloud-Talk-Signature` | If webhook_secret | HMAC signature |

**Request Body**: Nextcloud Talk payload

```json
{
  "type": "message",
  "conversation": {
    "token": "abc123",
    "name": "General"
  },
  "actor": {
    "type": "users",
    "id": "user123",
    "displayName": "John Doe"
  },
  "message": {
    "id": 12345,
    "message": "Hello from Nextcloud"
  }
}
```

**Response** (200 OK):

```json
{
  "status": "ok"
}
```

**Configuration Required**:

```toml
[channels_config.nextcloud_talk]
webhook_secret = "your_webhook_secret"
base_url = "https://nextcloud.example.com"
allowed_rooms = ["general", "support"]
```

---

## Endpoint Summary Table

| Endpoint | Method | Auth | Purpose | Use Case |
|----------|--------|------|---------|----------|
| `/health` | GET | None | Health check | Load balancers, monitoring |
| `/metrics` | GET | None | Prometheus metrics | Observability stack |
| `/pair` | POST | Pairing code | Get bearer token | Initial client setup |
| `/webhook` | POST | Bearer + Secret | Main messaging API | Direct API integration |
| `/whatsapp` | GET | None | WhatsApp verification | Meta webhook setup |
| `/whatsapp` | POST | Signature | WhatsApp messages | WhatsApp integration |
| `/linq` | POST | Signature | Linq messages | iMessage/RCS/SMS bridge |
| `/nextcloud-talk` | POST | Signature | Nextcloud Talk | Self-hosted chat |

---

## Security Features

### 1. Pairing System

```
Gateway Startup
    │
    ▼
┌─────────────────┐
│ Generate 6-digit │
│ Pairing Code    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Client POST     │────▶│ Validate Code   │
│ /pair           │     │ Issue Bearer    │
└─────────────────┘     │ Token           │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ Store Token     │
                        │ Persisted to    │
                        │ ~/.zeroclaw/    │
                        └─────────────────┘
```

### 2. Request Protection

| Layer | Mechanism | Config |
|-------|-----------|--------|
| Body Size | 64KB max | Hardcoded |
| Timeout | 30 seconds | Hardcoded |
| Rate Limit | Sliding window | `[gateway] rate_limit_per_minute` |
| Auth | Bearer token | `[gateway] require_pairing` |
| Extra | Webhook secret | `[channels_config.webhook] secret` |

### 3. Webhook Signature Verification

For WhatsApp, Linq, and Nextcloud:

```
Request
  │
  ▼
Extract Headers + Body
  │
  ▼
Compute HMAC-SHA256
  │
  ▼
Compare with Header
  │
  ├── Match ──▶ Process Message
  │
  └── Mismatch ──▶ 403 Forbidden
```

---

## Configuration

### Gateway Settings (`config.toml`)

```toml
[gateway]
port = 3000                    # HTTP server port
host = "127.0.0.1"            # Bind address (0.0.0.0 for public)
allow_public_bind = false     # Require explicit opt-in for 0.0.0.0
require_pairing = true        # Enable bearer token auth

[gateway.rate_limit]
enabled = true
per_minute = 100              # Requests per minute per IP
lockout_minutes = 5           # Lockout after exceeding

[channels_config.webhook]
secret = "optional_webhook_secret"  # Additional auth layer

[channels_config.whatsapp]
access_token = "EAABx..."
phone_number_id = "1234567890"
verify_token = "verify_me"
app_secret = "app_secret"
allowed_numbers = ["+1234567890"]

[channels_config.linq]
signing_secret = "linq_secret"

[channels_config.nextcloud_talk]
webhook_secret = "nc_secret"
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable description",
    "details": {
      "field": "additional context"
    }
  }
}
```

### Common HTTP Status Codes

| Code | Meaning | Typical Cause |
|------|---------|---------------|
| 200 | Success | Request processed |
| 400 | Bad Request | Invalid JSON, missing fields |
| 401 | Unauthorized | Missing/invalid token |
| 403 | Forbidden | Invalid pairing code, signature mismatch |
| 404 | Not Found | Endpoint doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 413 | Payload Too Large | Body > 64KB |
| 500 | Server Error | LLM failure, internal error |
| 503 | Service Unavailable | Gateway shutting down |

---

## Integration Patterns

### Pattern 1: Direct API

For programmatic access from applications:

```
App ──POST /pair──▶ Gateway (get token)
  │
  ├──POST /webhook──▶ Agent ──▶ LLM
  │                    │
  │◀───Response────────┘
  │
  └──Repeat with token...
```

### Pattern 2: Channel Bridge

For chat platform integration:

```
User ──Message──▶ Telegram
                    │
                    ▼
              Telegram Bot API
                    │
                    ▼
              ZeroClaw Channel
                    │
                    ▼
              POST /webhook
                    │
                    ▼
              Agent ──▶ LLM
                    │
                    ▼
              Reply via Telegram
```

### Pattern 3: Webhook Forwarding

For custom integrations:

```
External System
      │
      ├──POST /webhook (with idempotency key)
      │
      ├──POST /whatsapp (Meta verification)
      │
      └──POST /linq (SMS bridge)
            │
            ▼
        ZeroClaw Gateway
            │
            ▼
        Agent Processing
```

---

## Testing Examples

```bash
# 1. Health check
curl http://localhost:3000/health | jq

# 2. Get pairing token
curl -X POST http://localhost:3000/pair \
  -H "X-Pairing-Code: 732047" | jq '.token'

# 3. Send message
curl -X POST http://localhost:3000/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "Hello"}' | jq

# 4. WhatsApp verification
curl "http://localhost:3000/whatsapp?hub.mode=subscribe&hub.verify_token=$VERIFY_TOKEN&hub.challenge=test"

# 5. Check metrics
curl http://localhost:3000/metrics
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-03 | Initial API release |

---

**Related Documentation**:
- [ZeroClaw Configuration](https://github.com/openagen/zeroclaw/blob/main/docs/config-reference.md)
- [Channel Setup Guide](https://github.com/openagen/zeroclaw/blob/main/docs/channels-reference.md)
- [Security Best Practices](https://github.com/openagen/zeroclaw/blob/main/docs/security/README.md)
