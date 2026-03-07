# Minerva - Multi-Tenant Agent Runtime Platform

Minerva is an open-source platform for running ZeroClaw agents in distributed, multi-user environments with strong sandbox isolation. Deploy your own agent infrastructure with Daytona sandboxes, per-user isolation, and session continuity.

## Quick Links

- **[DEV-WORKFLOW.md](DEV-WORKFLOW.md)** - Complete deployment guide for developers
- **[Developer Setup Guide](docs/developer-setup-guide.md)** - End-to-end agent workflow tutorial

## Overview

- **Multi-user isolation**: Each user gets their own sandbox with filesystem-backed workspaces
- **ZeroClaw runtime**: Execute agents from identity files (`AGENT.md`, `SOUL.md`, `IDENTITY.md`)
- **Session continuity**: Workspaces persist across sessions with checkpoint/restore
- **Flexible deployment**: Local Docker Compose or cloud Daytona sandboxes
- **Typed event streaming**: Real-time SSE events for agent execution

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Initialize environment
uv run minerva init

# 3. Configure Daytona (required for sandbox execution)
cp .env.example .env
# Edit .env and add your DAYTONA_API_KEY

# 4. Start infrastructure
docker compose up -d postgres minio

# 5. Build ZeroClaw snapshot
uv run minerva snapshot build

# 6. Create and register agent pack
uv run minerva scaffold --out ./my-agent
uv run minerva register ./my-agent

# 7. Start server
uv run minerva serve
```

See [DEV-WORKFLOW.md](DEV-WORKFLOW.md) for complete deployment options including production guides.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client    │────▶│ Minerva API  │────▶│  Workspace Mgr  │
│ (X-User-ID) │     │              │     │                 │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                  │
                          ┌───────────────────────┼──────────┐
                          │                       │          │
                          ▼                       ▼          ▼
                   ┌──────────────┐      ┌──────────────┐  ┌──────────┐
                   │   Sandbox A  │      │   Sandbox B  │  │    S3    │
                   │ (user-alice) │      │  (user-bob)  │  │Checkpoints│
                   └──────────────┘      └──────────────┘  └──────────┘
```

## Development

### Prerequisites

- Python 3.11+ with `uv`
- Docker and Docker Compose
- Daytona API key ([get one here](https://daytona.io))

### Local Development

```bash
# Start PostgreSQL
docker compose up -d postgres

# Run migrations
uv run minerva migrate

# Start server with hot reload
uv run minerva serve
```

### Testing Multi-User Isolation

```bash
# User Alice - Gets isolated sandbox
curl -X POST http://localhost:8000/runs \
  -H "X-User-ID: alice@example.com" \
  -d '{"message": "Hello"}'

# User Bob - Different isolated sandbox
curl -X POST http://localhost:8000/runs \
  -H "X-User-ID: bob@example.com" \
  -d '{"message": "Hello"}'
```

## Documentation

- **[DEV-WORKFLOW.md](DEV-WORKFLOW.md)** - Complete deployment and configuration guide
- **[docs/developer-setup-guide.md](docs/developer-setup-guide.md)** - Step-by-step agent creation tutorial
- **API Docs** - Available at `/docs` when `DEBUG=true`

## License

[Add your license here]
