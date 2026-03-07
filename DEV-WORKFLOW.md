# Minerva Developer Workflow Guide

Deploy your own multi-tenant agent runtime with ZeroClaw. This guide covers everything from local development to production deployment.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Multi-User Setup](#multi-user-setup)
- [Agent Pack Development](#agent-pack-development)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

Minerva is an open-source, multi-tenant agent runtime platform. It provides:

- **Multi-user isolation**: Each user gets their own sandbox with filesystem-backed workspaces
- **Session continuity**: Workspaces persist across sessions with checkpoint/restore
- **ZeroClaw runtime**: Filesystem-centric agent execution with identity files (`AGENT.md`, `SOUL.md`, `IDENTITY.md`)
- **Flexible deployment**: Local Docker Compose or cloud Daytona sandboxes
- **Typed event streaming**: Real-time SSE events for agent execution

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Agent Pack** | Folder containing `AGENT.md`, `SOUL.md`, `IDENTITY.md`, and `skills/` that defines an agent |
| **Workspace** | Persistent user-scoped environment (1 per developer, shared by all their end-users) |
| **Sandbox** | Isolated execution environment provisioned per (workspace_id, external_user_id) pair |
| **ZeroClaw** | Runtime that executes agents from filesystem identity files |
| **Checkpoint** | Immutable workspace snapshots stored in S3-compatible storage |

---

## Architecture

```mermaid
flowchart TB
    subgraph Client
        U[User/API Client]
    end

    subgraph Minerva[Minerva Control Plane]
        API[FastAPI Server]
        Auth[Identity Resolution]
        WM[Workspace Manager]
        SO[Sandbox Orchestrator]
    end

    subgraph Storage
        DB[(PostgreSQL)]
        S3[S3/MinIO Checkpoints]
    end

    subgraph Daytona[Daytona Sandbox Provider]
        SB1[Sandbox: user-alice]
        SB2[Sandbox: user-bob]
        VOL[Volume: Agent Pack Files]
    end

    U -->|X-User-ID| API
    API --> Auth
    Auth -->|Resolve workspace| WM
    WM -->|Get/Create Sandbox| SO
    SO -->|Provision| SB1
    SO -->|Provision| SB2
    SO -->|Sync Files| VOL
    WM --> DB
    WM --> S3
    SB1 -->|Mount| VOL
    SB2 -->|Mount| VOL
```

### Runtime Flow

1. **Request** → API with `X-User-ID` header
2. **Identity Resolution** → Map to developer workspace + external identity
3. **Sandbox Routing** → Find existing sandbox or provision new one
4. **Execution** → ZeroClaw gateway processes message in isolated sandbox
5. **Events** → SSE stream returns typed events (message, tool_call, state_update)
6. **Persistence** → Optional checkpoint to S3 at milestones

---

## Prerequisites

- **Python**: 3.11+ with `uv` package manager
- **Docker**: 20.10+ with Docker Compose
- **Daytona**: API key for sandbox provisioning ([get one here](https://daytona.io))
- **Git**: For cloning and agent pack management

### Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

---

## Quick Start

```bash
# 1. Clone repository
git clone <your-fork-or-repo>
cd minerva

# 2. Install dependencies
uv sync

# 3. Initialize environment
uv run minerva init

# 4. Copy and edit environment
cp .env.example .env
# Edit .env with your Daytona API key

# 5. Start infrastructure
docker compose up -d postgres minio

# 6. Run migrations
uv run minerva migrate

# 7. Build ZeroClaw snapshot
uv run minerva snapshot build

# 8. Scaffold and register agent pack
uv run minerva scaffold --out ./my-agent
uv run minerva register ./my-agent

# 9. Start server
uv run minerva serve
```

---

## Local Development

### 1. Environment Setup

```bash
# Copy example environment
cp .env.example .env

# Required minimum configuration:
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw

# Daytona (required for sandbox execution)
DAYTONA_API_KEY=your-daytona-api-key
SANDBOX_PROFILE=daytona

# Workspace (auto-created on first register)
MINERVA_WORKSPACE_ID=auto

# Debug
DEBUG=true
LOG_LEVEL=DEBUG
EOF
```

### 2. Start Dependencies

```bash
# Start PostgreSQL and MinIO
docker compose up -d postgres minio

# Verify status
docker compose ps

# View logs
docker compose logs -f postgres
```

### 3. Database Setup

```bash
# Run migrations
uv run minerva migrate

# Verify with preflight
uv run minerva init
```

### 4. Build ZeroClaw Snapshot

```bash
# Configure Picoclaw source (ZeroClaw is compatible with Picoclaw repos)
echo 'PICOCLAW_REPO_URL=https://github.com/your-org/zeroclaw-runtime.git' >> .env
echo 'PICOCLAW_REPO_REF=main' >> .env

# Build snapshot (15-30 minutes first run)
uv run minerva snapshot build

# Note the snapshot name from output and add to .env:
# DAYTONA_PICOCLAW_SNAPSHOT_NAME=zeroclaw-main-abc123
```

### 5. Development Server

```bash
# Start with auto-reload
uv run minerva serve

# Or with explicit host/port
uv run minerva serve --host 0.0.0.0 --port 8000
```

---

## Production Deployment

### Option 1: Daytona Cloud (Recommended)

**Best for**: Production workloads, auto-scaling, managed infrastructure

```bash
# .env configuration
SANDBOX_PROFILE=daytona
DAYTONA_API_KEY=your-production-api-key
DAYTONA_TARGET=us  # or eu, asia
DAYTONA_BASE_IMAGE=daytonaio/workspace-picoclaw@sha256:abc123...
DAYTONA_BASE_IMAGE_STRICT_MODE=true
```

**Deployment Steps**:

```bash
# 1. Build production snapshot with pinned digest
DAYTONA_BASE_IMAGE_STRICT_MODE=true uv run minerva snapshot build

# 2. Register agent pack
uv run minerva register ./production-agent

# 3. Start with production settings
DEBUG=false
LOG_LEVEL=INFO
PROMETHEUS_ENABLED=true
```

### Option 2: Docker Compose (Self-Hosted)

**Best for**: On-premise, air-gapped, or cost-sensitive deployments

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  minerva:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+psycopg://picoclaw:${DB_PASSWORD}@postgres:5432/picoclaw
      - DAYTONA_API_KEY=${DAYTONA_API_KEY}
      - SANDBOX_PROFILE=daytona
    depends_on:
      - postgres
      - minio
    volumes:
      - ./agent-packs:/app/agent-packs:ro

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: picoclaw
      POSTGRES_USER: picoclaw
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

**Deploy**:

```bash
# Copy production environment
cp .env.example .env.production
# Edit with production values

# Deploy
docker compose -f docker-compose.prod.yml up -d
```

### Option 3: Kubernetes

**Best for**: Large-scale, multi-region, enterprise deployments

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minerva-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: minerva-api
  template:
    metadata:
      labels:
        app: minerva-api
    spec:
      containers:
      - name: api
        image: your-registry/minerva:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: minerva-secrets
              key: database-url
        - name: DAYTONA_API_KEY
          valueFrom:
            secretKeyRef:
              name: minerva-secrets
              key: daytona-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

---

## Multi-User Setup

Minerva uses a **developer-centric** tenancy model:

- **1 Developer** → 1 Workspace (in `users` table)
- **N End-Users** → Resolved to developer's workspace via `external_identities` table
- **Sandbox Isolation** → Per (workspace_id, external_user_id) pair

### Identity Resolution Flow

```
Request (X-User-ID: alice@example.com)
    ↓
Developer Workspace (MINERVA_WORKSPACE_ID)
    ↓
External Identity Lookup (external_user_id = alice@example.com)
    ↓
Sandbox Key: (workspace_id, alice@example.com) → Sandbox A
    ↓
Different X-User-ID → Sandbox B (isolated)
```

### Configure Multi-User Mode

```bash
# .env
MINERVA_WORKSPACE_ID=your-workspace-uuid
GUEST_ID=guest  # Optional: value treated as ephemeral guest
```

### Test Multi-User Isolation

```bash
# User Alice - Gets Sandbox A
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: alice@company.com" \
  -H "X-Session-ID: session-1" \
  -d '{"message": "Hello from Alice"}'

# User Bob - Gets Sandbox B (isolated from Alice)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: bob@company.com" \
  -H "X-Session-ID: session-2" \
  -d '{"message": "Hello from Bob"}'

# Same user, new session - Reuses Sandbox A
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: alice@company.com" \
  -H "X-Session-ID: session-3" \
  -d '{"message": "Follow-up from Alice"}'
```

### Guest Mode

For unauthenticated or anonymous users:

```bash
# Guest request (no DB record, ephemeral sandbox)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -H "X-User-ID: guest" \
  -d '{"message": "Anonymous query"}'
```

**Guest behavior**:
- No `external_identities` row created
- Ephemeral sandbox (no session continuity)
- No checkpoint persistence

---

## Agent Pack Development

### Folder Structure

```
my-agent/
├── AGENT.md          # Core identity and capabilities
├── SOUL.md           # Personality and behavior
├── IDENTITY.md       # Metadata (name, version, author)
└── skills/           # Optional skill definitions
    ├── code-review/
    │   └── SKILL.md
    └── web-search/
        └── SKILL.md
```

### AGENT.md Template

```markdown
# Agent: DevAssistant

## Role
Senior software engineer assistant specializing in code review and debugging.

## Capabilities
- Analyze code for bugs and security issues
- Suggest performance improvements
- Explain complex code patterns
- Write unit tests

## Constraints
- Do not execute code without user confirmation
- Always provide citations for external knowledge
```

### SOUL.md Template

```markdown
# Soul Configuration

## Personality
Professional, thorough, and educational.

## Communication Style
- Lead with key findings
- Provide code examples in fenced blocks
- Ask clarifying questions when context is ambiguous
- Use technical terminology appropriate to the audience

## Tone Guidelines
- Encouraging but honest about issues
- Patient with beginner questions
- Concise in explanations
```

### IDENTITY.md Template

```markdown
# Identity

## Name
DevAssistant

## Version
1.0.0

## Author
Your Name <your.email@example.com>

## Description
AI assistant for software development tasks

## Tags
programming, code-review, debugging, python
```

### Scaffold New Pack

```bash
# Create template
uv run minerva scaffold --out ./my-new-agent

# Edit files
nano my-new-agent/AGENT.md
nano my-new-agent/SOUL.md
nano my-new-agent/IDENTITY.md

# Register
uv run minerva register ./my-new-agent
```

### Update Existing Pack

```bash
# Edit files, then re-register (updates are idempotent)
uv run minerva register ./my-agent
```

---

## Configuration Reference

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+psycopg://user:pass@host/db` |
| `DAYTONA_API_KEY` | Daytona API authentication | `dnt_...` |
| `MINERVA_WORKSPACE_ID` | Developer workspace UUID | `auto` or `uuid` |

### Daytona Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_PROFILE` | `daytona` | Provider: `daytona` or `local_compose` |
| `DAYTONA_TARGET` | `us` | Region: `us`, `eu`, `asia` |
| `DAYTONA_BASE_IMAGE` | `daytonaio/workspace-picoclaw:latest` | Sandbox base image |
| `DAYTONA_BASE_IMAGE_STRICT_MODE` | `false` | Enforce digest-pinned images |
| `DAYTONA_AUTO_STOP_INTERVAL` | `0` | Auto-stop seconds (0 = disabled) |

### Snapshot Configuration

| Variable | Description |
|----------|-------------|
| `PICOCLAW_REPO_URL` | Git URL for ZeroClaw runtime source |
| `PICOCLAW_REPO_REF` | Branch/tag/commit (default: `main`) |
| `DAYTONA_PICOCLAW_SNAPSHOT_NAME` | Snapshot name from `snapshot build` |

### S3 Checkpoint Storage

| Variable | Description |
|----------|-------------|
| `CHECKPOINT_ENABLED` | Enable checkpoint persistence (`true`/`false`) |
| `CHECKPOINT_S3_BUCKET` | S3 bucket name |
| `CHECKPOINT_S3_ENDPOINT` | S3-compatible endpoint (empty for AWS) |
| `CHECKPOINT_S3_REGION` | AWS region (default: `us-east-1`) |
| `CHECKPOINT_S3_ACCESS_KEY` | S3 access key |
| `CHECKPOINT_S3_SECRET_KEY` | S3 secret key |
| `CHECKPOINT_MILESTONE_INTERVAL_SECONDS` | Checkpoint interval (default: 300) |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `PROMETHEUS_ENABLED` | `false` | Enable `/metrics` endpoint |
| `DEBUG` | `false` | Enable `/docs` and `/redoc` |

### Identity

| Variable | Description |
|----------|-------------|
| `GUEST_ID` | X-User-ID value treated as guest (ephemeral) |

---

## API Reference

### POST /runs

Execute an agent run with streaming response.

**Headers**:
- `Content-Type: application/json`
- `X-User-ID: <user-identifier>` (required)
- `X-Session-ID: <session-identifier>` (optional, for continuity)

**Request Body**:
```json
{
  "message": "Hello, agent!",
  "agent_pack_id": "optional-pack-uuid",
  "stream": true
}
```

**Response** (SSE Stream):
```
event: provisioning
data: {"status": "creating_sandbox", "message": "Creating sandbox..."}

event: running
data: {"status": "active", "message": "Agent executing"}

event: message
data: {"role": "assistant", "content": "Hello! How can I help?"}

event: completed
data: {"status": "completed", "run_id": "uuid"}
```

### GET /health

Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "daytona": "healthy"
  }
}
```

### GET /metrics

Prometheus metrics (when `PROMETHEUS_ENABLED=true`).

---

## Troubleshooting

### Issue: "DAYTONA_API_KEY not configured"

```bash
# Solution: Add to .env
echo 'DAYTONA_API_KEY=your-key-here' >> .env

# Verify
uv run minerva init
```

### Issue: "Workspace has no registered agent packs"

```bash
# Solution: Register an agent pack
uv run minerva scaffold --out ./my-agent
uv run minerva register ./my-agent
```

### Issue: "Snapshot not found"

```bash
# Solution: Build snapshot first
uv run minerva snapshot build

# Then add to .env
echo 'DAYTONA_PICOCLAW_SNAPSHOT_NAME=the-snapshot-name' >> .env
```

### Issue: Database connection failed

```bash
# Solution: Start postgres
docker compose up -d postgres

# Wait for healthcheck
sleep 10

# Run migrations
uv run minerva migrate
```

### Issue: Sandbox provisioning timeout

**Check**:
1. Daytona API key is valid
2. `DAYTONA_PICOCLAW_SNAPSHOT_NAME` is set correctly
3. Network connectivity to Daytona API

```bash
# Test Daytona connectivity
curl -H "Authorization: Bearer $DAYTONA_API_KEY" \
  https://api.daytona.io/v1/workspaces
```

### Issue: Per-user sandbox not isolated

**Check**:
- Verify `X-User-ID` header is different for different users
- Check sandbox routing logs
- Ensure external identity resolution is working

```bash
# Check workspace configuration
curl http://localhost:8000/health

# Test with different users and check logs
LOG_LEVEL=DEBUG uv run minerva serve
```

### Issue: Agent pack files not found in sandbox

**Check**:
1. Pack is registered: `uv run minerva register ./my-agent`
2. Volume sync completed (check logs)
3. Identity files are readable

```bash
# Re-register to force sync
uv run minerva register ./my-agent
```

---

## Next Steps

- **Production Hardening**: Enable strict mode, Prometheus metrics, digest-pinned images
- **Custom Skills**: Add skill definitions in `skills/` folder
- **Checkpoint Strategy**: Configure S3 for session persistence
- **Monitoring**: Set up alerts for sandbox provisioning failures
- **Scaling**: Deploy with multiple API replicas behind a load balancer

---

## Resources

- [Daytona Documentation](https://www.daytona.io/docs/)
- [ZeroClaw Runtime](https://github.com/your-org/zeroclaw-runtime)
- [Minerva Issues](https://github.com/your-org/minerva/issues)

---

**Ready to deploy?** Start with [Local Development](#local-development) and progress to [Production Deployment](#production-deployment) when ready.
