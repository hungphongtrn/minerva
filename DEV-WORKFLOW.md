# Minerva Development Workflow

## Prerequisites

| Dependency | Version | Check |
|-----------|---------|-------|
| Python | ≥ 3.12 | `python3 --version` |
| uv | Latest | `uv --version` |
| Docker Compose | v2+ | `docker compose version` |
| PostgreSQL client | Any | `psql --version` *(optional)* |

## Quick Start

### 1. Install dependencies

```bash
uv sync --dev
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set at minimum:
#   DATABASE_URL=postgresql+psycopg://minerva:minerva@localhost:5432/minerva
#   SANDBOX_PROFILE=local_compose  (or "daytona" if you have a Daytona API key)
```

### 3. Start infrastructure

```bash
docker compose up -d postgres minio
```

### 4. Run database migrations

```bash
uv run minerva migrate
```

### 5. Start the dev server

```bash
uv run minerva serve
# Server runs at http://localhost:8000
# Health check: curl http://localhost:8000/health
```

### 6. Run tests

```bash
uv run pytest src/tests/ -v --timeout=30
```

### 7. Lint & format

```bash
uv run ruff check src/ --fix
uv run ruff format src/
```

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  API Layer                       │
│  POST /runs (SSE)  │  Agent Packs  │  Health    │
└────────┬───────────┴──────────────┴────────────┘
         │
┌────────▼───────────────────────────────────────┐
│              Service Layer                      │
│  RunService → WorkspaceLifecycle → Orchestrator │
└────────┬───────────────────────────────────────┘
         │
┌────────▼───────────────────────────────────────┐
│           Infrastructure Layer                  │
│  Daytona Provider  │  Local Compose Provider   │
└────────────────────┴───────────────────────────┘
```

**Key invariant:** 1 user → 1 sandbox. Multi-user = multi-sandbox.

### Request flow

1. `POST /runs` with `X-User-ID` header
2. Per-user queue serializes requests (`OssUserQueue`)
3. `RunService.execute_with_routing()` resolves workspace → sandbox
4. `SandboxOrchestratorService.resolve_sandbox()` finds or provisions sandbox
5. ZeroClaw gateway executes the agent runtime inside the sandbox
6. SSE events stream back to the client

### Sandbox lifecycle

- **Provisioning:** Single-attempt. No retry amplification.
- **Routing:** Health-aware. Prefer active healthy sandbox. Exclude unhealthy.
- **Idle TTL:** Sandboxes stopped after configurable idle period (default: 1 hour).
- **Checkpoints:** Memory/session state only. Static identity files mounted at creation.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `SANDBOX_PROFILE` | No | `local_compose` | `local_compose` or `daytona` |
| `DAYTONA_API_KEY` | If daytona | — | Daytona Cloud API key |
| `DAYTONA_API_URL` | No | Cloud default | Self-hosted Daytona URL |
| `DAYTONA_PICOCLAW_SNAPSHOT_NAME` | No | `picoclaw-snapshot` | Daytona snapshot for provisioning |
| `SANDBOX_IDLE_TTL_SECONDS` | No | `3600` | Idle TTL before sandbox stop |

## CLI Commands

```bash
uv run minerva serve         # Start the API server
uv run minerva migrate       # Run database migrations
uv run minerva init           # Initialize .env from template
```

## Tear Down

```bash
docker compose down -v        # Stop and remove all containers + volumes
```

## Code Standards

- **Linter/Formatter:** ruff (configured in `pyproject.toml`)
- **Max file size:** 300 lines per module
- **Type hints:** Required on all public APIs
- **Tests:** `src/tests/` — run with `uv run pytest`
- **Package manager:** uv (never pip)
