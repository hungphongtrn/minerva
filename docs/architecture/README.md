# Minerva Architecture Overview

**Last Updated:** March 8, 2026  
**Project:** Picoclaw/ZeroClaw Multi-tenant OSS Runtime  
**Status:** Active Development

---

## Quick Reference

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **API Layer** | HTTP endpoints, request/response handling | `src/api/` |
| **Service Layer** | Business logic, orchestration | `src/services/` |
| **Infrastructure Layer** | Provider adapters, external integrations | `src/infrastructure/` |
| **Data Layer** | Models, repositories, database | `src/db/` |
| **Runtime Policy** | Security enforcement, policy decisions | `src/runtime_policy/` |
| **Authorization** | Authentication, guards, permissions | `src/authorization/` |

---

## Table of Contents

- [Directory Structure](#directory-structure)
- [Key Concepts](#key-concepts)
- [Architecture Layers](#architecture-layers)
- [State Machines](./state-machines.md)
- [Execution Flow](./execution-flow.md)
- [Component Catalog](./component-catalog.md)
- [Dead Code & Legacy](./dead-code-legacy.md)

---

## Directory Structure

```
src/
├── api/                        # HTTP API Layer
│   ├── router.py              # Main API router (/api/v1)
│   ├── dependencies/          # FastAPI dependencies (auth, DB)
│   ├── routes/                # Business API endpoints
│   │   ├── runs.py           # Run execution endpoints
│   │   ├── workspaces.py     # Workspace management
│   │   ├── agent_packs.py    # Agent pack CRUD
│   │   ├── api_keys.py       # API key management
│   │   ├── persistence.py    # State persistence endpoints
│   │   └── ...
│   └── oss/                   # OSS (end-user) endpoints
│       ├── router.py         # OSS router (root level)
│       └── routes/
│           ├── health.py     # /health, /ready
│           ├── metrics.py    # /metrics
│           └── runs.py       # /runs (SSE streaming)
│
├── services/                  # Business Logic Layer
│   ├── run_service.py        # Main run execution orchestrator
│   ├── sandbox_orchestrator_service.py  # Sandbox routing/lifecycle
│   ├── workspace_lifecycle_service.py   # Workspace + lease management
│   ├── workspace_lease_service.py       # Write lease coordination
│   ├── sandbox_gateway_service.py       # ZeroClaw gateway client
│   ├── zeroclaw_gateway_service.py      # Legacy gateway (to be unified)
│   ├── oss_user_queue.py     # Per-user request serialization
│   ├── oss_sse_events.py     # SSE event formatting
│   ├── preflight_service.py  # Preflight checks
│   ├── agent_pack_service.py # Agent pack management
│   └── checkpoint_*.py       # Checkpoint lifecycle services
│
├── infrastructure/            # External Integrations
│   ├── sandbox/
│   │   └── providers/
│   │       ├── base.py       # Provider interface/protocol
│   │       ├── factory.py    # Provider factory
│   │       ├── daytona.py    # Daytona Cloud provider
│   │       └── local_compose.py  # Docker Compose provider
│   └── checkpoints/
│       └── s3_checkpoint_store.py  # S3 checkpoint storage
│
├── db/                        # Data Layer
│   ├── models.py             # SQLAlchemy models (all entities)
│   ├── session.py            # Database session management
│   ├── rls_context.py        # Row-level security context
│   └── repositories/         # Data access layer
│       ├── sandbox_instance_repository.py
│       ├── workspace_lease_repository.py
│       ├── run_session_repository.py
│       └── ...
│
├── runtime_policy/            # Security & Policy
│   ├── models.py             # Policy data models
│   ├── enforcer.py           # Policy enforcement logic
│   └── engine.py             # Policy evaluation engine
│
├── authorization/             # Authentication
│   ├── guards.py             # Auth guards/decorators
│   └── policy.py             # Authorization policies
│
├── identity/                  # Identity Management
│   ├── repository.py         # User/workspace lookups
│   ├── key_material.py       # API key hashing/validation
│   └── service.py            # Identity operations
│
├── guest/                     # Guest Mode
│   └── identity.py           # Guest principal handling
│
├── integrations/              # Integration Specifications
│   ├── zeroclaw/             # ZeroClaw runtime spec
│   └── sandbox_runtime/      # Sandbox runtime spec
│
├── config/                    # Configuration
│   └── settings.py           # Pydantic settings
│
├── cli/                       # CLI Commands
│   ├── main.py               # CLI entry point
│   └── commands/
│       ├── serve.py          # Start API server
│       ├── init.py           # Initialize workspace
│       ├── register.py       # Register developer
│       ├── scaffold.py       # Scaffold agent pack
│       └── ...
│
└── tests/                     # Test Suite
    ├── services/             # Service unit tests
    ├── integration/          # Integration tests
    ├── smoke/                # Smoke/e2e tests
    └── cli/                  # CLI tests
```

---

## Key Concepts

### 1. Multi-Tenancy Model

Minerva implements workspace-based multi-tenancy:

- **Workspace**: Primary tenant boundary (1 user → 1 workspace in OSS mode)
- **External Identity**: End-user within a workspace scope
- **Sandbox**: Execution environment per (workspace, external_user) pair
- **Agent Pack**: Deployable agent configuration with identity

### 2. Execution Modes

| Mode | Description | Persistence |
|------|-------------|-------------|
| **Guest** | Unauthenticated, ephemeral | None (in-memory only) |
| **Authenticated** | API key authenticated | Full (runs, checkpoints, events) |
| **OSS** | External end-user via /runs | Scoped to workspace |

### 3. Core Abstractions

- **Run**: Single execution request with policy context
- **RunSession**: Persistent record of a run (non-guest only)
- **SandboxInstance**: Database record of provisioned sandbox
- **WorkspaceLease**: Write lock for workspace serialization
- **Checkpoint**: Workspace state snapshot for recovery

---

## Architecture Layers

### Layer 1: API Layer (`src/api/`)

**Responsibilities:**
- HTTP request/response handling
- Input validation (Pydantic models)
- Authentication/authorization enforcement
- Dependency injection

**Key Patterns:**
- FastAPI routers with explicit prefixes
- Separate OSS router for end-user endpoints
- Dependency functions for auth and DB sessions

### Layer 2: Service Layer (`src/services/`)

**Responsibilities:**
- Business logic orchestration
- Cross-cutting concerns (leasing, routing, policy)
- Provider-agnostic operations

**Key Services:**

| Service | Purpose | Lines |
|---------|---------|-------|
| `run_service.py` | Run execution with routing/policy | ~820 |
| `sandbox_orchestrator_service.py` | Sandbox selection & provisioning | ~859 |
| `workspace_lifecycle_service.py` | Workspace + lease coordination | ~552 |
| `sandbox_gateway_service.py` | Gateway communication | ~600+ |

**Design Principles:**
- Single-attempt provisioning (no retry amplification)
- Deterministic lease cleanup (try/finally pattern)
- Fail-fast with clear error types

### Layer 3: Infrastructure Layer (`src/infrastructure/`)

**Responsibilities:**
- Provider-specific implementations
- External system integration
- Abstract away provider differences

**Provider Pattern:**
```python
# Provider protocol (base.py)
class SandboxProvider(ABC):
    async def provision_sandbox(config) -> SandboxInfo
    async def get_health(ref) -> SandboxInfo
    async def stop_sandbox(ref) -> SandboxInfo
```

**Supported Providers:**
- **Daytona**: Cloud/self-hosted Daytona workspaces
- **Local Compose**: Docker Compose for development

### Layer 4: Data Layer (`src/db/`)

**Responsibilities:**
- Entity definitions (SQLAlchemy models)
- Data access (repository pattern)
- Migration management (Alembic)

**Key Models:**
- `User`, `Workspace`, `Membership` - Identity
- `SandboxInstance` - Sandbox lifecycle
- `WorkspaceLease` - Lease coordination
- `RunSession` - Run persistence
- `WorkspaceCheckpoint` - State snapshots

---

## Quick Start for Developers

1. **Start here:** [`execution-flow.md`](./execution-flow.md) to understand request flow
2. **Understand states:** [`state-machines.md`](./state-machines.md) for lifecycle diagrams
3. **Find components:** [`component-catalog.md`](./component-catalog.md) for detailed reference
4. **Cleanup tasks:** [`dead-code-legacy.md`](./dead-code-legacy.md) for maintenance

---

## Architecture Statistics

- **Total Python files:** 161
- **Service layer LOC:** ~9,591
- **Database models:** 15 entities
- **API endpoints:** 40+ routes
- **Test files:** 20+ test modules

---

## Related Documentation

- [Coding Standards](../CODING_STANDARDS.md)
- [OSS Spec](../OSS_SPEC.md)
- [Project State Capture](./8-3-25-PROJECT_STATE_CAPTURE.md)
