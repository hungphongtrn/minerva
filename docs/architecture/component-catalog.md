# Component Catalog

**Detailed reference for all major Minerva components.**

---

## Table of Contents

1. [Services](#services)
2. [Repositories](#repositories)
3. [Models](#models)
4. [Providers](#providers)
5. [API Routes](#api-routes)

---

## Services

### RunService

**File:** `src/services/run_service.py`  
**Lines:** ~820  
**Purpose:** Central orchestrator for run execution with routing and policy enforcement.

**Key Methods:**

| Method | Purpose | Lines |
|--------|---------|-------|
| `execute_with_routing()` | Main entrypoint - routes and executes | ~100 |
| `resolve_routing_target()` | Resolves workspace + sandbox | ~80 |
| `_execute_via_gateway()` | Single-attempt gateway execution | ~70 |
| `execute_run()` | Policy enforcement | ~50 |
| `_process_routing_target()` | Converts lifecycle target to routing result | ~60 |

**Dependencies:**
- `WorkspaceLifecycleService` - Workspace + lease management
- `RuntimeEnforcer` - Policy enforcement
- `RuntimePersistenceService` - Run persistence
- `SandboxGatewayService` - Gateway communication

**State Mutations:**
- Creates `RunSession` records
- Acquires/releases workspace leases
- Updates session state (QUEUED → RUNNING → COMPLETED/FAILED)

---

### SandboxOrchestratorService

**File:** `src/services/sandbox_orchestrator_service.py`  
**Lines:** ~859  
**Purpose:** Sandbox selection, provisioning, and lifecycle orchestration.

**Key Methods:**

| Method | Purpose | Lines |
|--------|---------|-------|
| `resolve_sandbox()` | Main routing logic | ~120 |
| `apply_ttl_cleanup()` | Stop idle sandboxes | ~50 |
| `_route_to_existing()` | Find healthy existing sandbox | ~40 |
| `_provision_with_timeout()` | Provision new sandbox | ~60 |
| `_check_layered_readiness()` | Health + identity checks | ~80 |

**Core Algorithm:**
```
1. Apply TTL cleanup
2. Find existing healthy sandbox → route
3. No healthy sandbox → provision one new
4. Fail fast on provision failure
```

**RoutingResult Enum:**
- `ROUTED_EXISTING` - Used existing healthy sandbox
- `PROVISIONED_NEW` - Created new sandbox
- `HYDRATED_EXISTING` - Restored from checkpoint
- `UNHEALTHY_EXCLUDED` - Unhealthy sandboxes removed
- `NO_HEALTHY_CANDIDATES` - No viable sandboxes
- `PROVISION_FAILED` - Provisioning error

---

### WorkspaceLifecycleService

**File:** `src/services/workspace_lifecycle_service.py`  
**Lines:** ~552  
**Purpose:** High-level workspace lifecycle with lease coordination.

**Key Methods:**

| Method | Purpose | Lines |
|--------|---------|-------|
| `resolve_target()` | Main entrypoint - get workspace + sandbox | ~150 |
| `_resolve_workspace()` | Get/create workspace for principal | ~40 |
| `_execute_orchestration()` | Run orchestrator with retry | ~80 |
| `is_restore_in_progress()` | Check restore state | ~20 |

**LifecycleTarget:**
```python
@dataclass
class LifecycleTarget:
    workspace: Workspace
    lease_acquired: bool
    lease_result: LeaseAcquisitionResult
    sandbox: SandboxInstance
    routing_result: SandboxRoutingResult
    error: Optional[str]
    restore_state: Optional[str]  # "none", "in_progress", "completed"
    queued: bool
```

**Restore Tracking:**
- Class-level `_restore_in_progress` dict prevents duplicate restores
- Key: `workspace_id` → Value: `{started_at, checkpoint_id}`

---

### WorkspaceLeaseService

**File:** `src/services/workspace_lease_service.py`  
**Lines:** ~200  
**Purpose:** Single-writer coordination for workspaces.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `acquire_lease()` | Try to get write lock |
| `release_lease()` | Release write lock |
| `is_lease_active()` | Check if lease is held |

**LeaseResult Enum:**
- `ACQUIRED` - Lease obtained
- `CONFLICT` - Another holder has active lease
- `EXPIRED` - Reclaimed expired lease
- `RELEASED` - Successfully released

**Database Schema:**
```sql
workspace_leases:
  - workspace_id (PK, FK)
  - holder_run_id
  - holder_identity
  - acquired_at
  - expires_at
  - version (optimistic locking)
```

---

### SandboxGatewayService

**File:** `src/services/sandbox_gateway_service.py`  
**Lines:** ~600  
**Purpose:** Communicate with ZeroClaw runtime in sandboxes.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `execute()` | Execute message via gateway |
| `health_check()` | Check gateway health |
| `stream_events()` | Parse SSE stream from runtime |

**GatewayResult:**
```python
@dataclass
class GatewayResult:
    success: bool
    output: Optional[dict]  # Parsed response
    events: List[dict]      # SSE events
    error: Optional[GatewayError]
```

**Error Types:**
- `AUTH_ERROR` - Token invalid/expired
- `TRANSPORT_ERROR` - Network failure
- `UPSTREAM_ERROR` - Runtime error
- `TIMEOUT` - Execution timeout
- `MALFORMED_RESPONSE` - Parse error

---

### ZeroclawGatewayService

**File:** `src/services/zeroclaw_gateway_service.py`  
**Lines:** ~650  
**Purpose:** Legacy gateway service (being unified with SandboxGatewayService).

**Status:** ⚠️ To be consolidated

**Differences from SandboxGatewayService:**
- Additional retry logic (deprecated)
- Token rotation handling
- Different error categorization

**Migration Path:**
1. Move all token logic to SandboxGatewayService
2. Deprecate this service
3. Update all callers

---

### OSS Services

#### OssUserQueue

**File:** `src/services/oss_user_queue.py`  
**Lines:** ~300  
**Purpose:** Per-user request serialization for OSS endpoint.

**Key Features:**
- Per-user lock ensures sequential execution
- Idempotency caching
- Cold start detection (inside lock)

**Usage:**
```python
queue_result = await user_queue.execute(
    user_id=principal.external_user_id,
    idempotency_key=idempotency_key,
    operation=execute_operation,
)
```

#### OssSseEventBuilder

**File:** `src/services/oss_sse_events.py`  
**Lines:** ~400  
**Purpose:** Build SSE-formatted events for streaming responses.

**Event Types:**
- `queued` - Request queued
- `provisioning` - Sandbox provisioning
- `running` - Execution started
- `message` - Output chunk
- `completed` - Success
- `failed` - Error

---

## Repositories

### SandboxInstanceRepository

**File:** `src/db/repositories/sandbox_instance_repository.py`  
**Lines:** ~450  
**Purpose:** Data access for sandbox instances.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `get_by_id()` | Get sandbox by UUID |
| `get_by_provider_ref()` | Get by provider reference |
| `list_by_workspace()` | All sandboxes for workspace |
| `list_active_by_workspace()` | Active sandboxes only |
| `update_state()` | Atomic state transition |
| `update_health()` | Update health status |

**Query Patterns:**
```python
# Active healthy sandboxes
session.query(SandboxInstance)
    .filter_by(workspace_id=workspace_id, state=SandboxState.ACTIVE)
    .filter(SandboxInstance.health_status == SandboxHealthStatus.HEALTHY)
```

---

### WorkspaceLeaseRepository

**File:** `src/db/repositories/workspace_lease_repository.py`  
**Lines:** ~200  
**Purpose:** Data access for workspace leases.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `get_active_lease()` | Get current lease for workspace |
| `acquire_lease()` | Insert/update lease with optimistic locking |
| `release_lease()` | Mark lease released |
| `get_expired_leases()` | Find reclaimable leases |

---

### RunSessionRepository

**File:** `src/db/repositories/run_session_repository.py`  
**Lines:** ~300  
**Purpose:** Data access for run sessions.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `create()` | Create new run session |
| `get_by_run_id()` | Get by unique run_id |
| `update_state()` | Transition state |
| `list_by_workspace()` | List runs for workspace |

---

### WorkspaceCheckpointRepository

**File:** `src/db/repositories/workspace_checkpoint_repository.py`  
**Lines:** ~350  
**Purpose:** Data access for checkpoints.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `create()` | Create checkpoint record |
| `get_active_for_workspace()` | Get active checkpoint pointer |
| `update_state()` | Transition checkpoint state |
| `get_fallback_chain()` | Get fallback chain |

---

## Models

### Core Entities

#### User

**Table:** `users`  
**Purpose:** Developer account (workspace owner).

```python
class User(Base):
    id: UUID
    email: str (unique)
    hashed_password: Optional[str]
    is_active: bool
    is_guest: bool
    created_at: datetime
```

#### Workspace

**Table:** `workspaces`  
**Purpose:** Tenant boundary for multi-tenancy.

```python
class Workspace(Base):
    id: UUID
    name: str
    slug: str (unique)
    owner_id: UUID (FK → users)
    is_active: bool
```

#### ExternalIdentity

**Table:** `external_identities`  
**Purpose:** End-user identity scoped to workspace.

```python
class ExternalIdentity(Base):
    workspace_id: UUID (PK, FK)
    external_user_id: str (PK)
    created_at: datetime
    
    # Composite: (workspace_id, external_user_id)
```

---

### Lifecycle Entities

#### SandboxInstance

**Table:** `sandbox_instances`  
**Purpose:** Tracks sandbox state and health.

```python
class SandboxInstance(Base):
    id: UUID
    workspace_id: UUID (FK)
    external_user_id: Optional[str]  # OSS mode
    profile: SandboxProfile
    provider_ref: str
    state: SandboxState
    health_status: SandboxHealthStatus
    last_health_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    idle_ttl_seconds: int
    gateway_url: Optional[str]
    bridge_auth_token: Optional[str]
    identity_ready: bool
    hydration_status: SandboxHydrationStatus
```

#### WorkspaceLease

**Table:** `workspace_leases`  
**Purpose:** Write lock for workspace serialization.

```python
class WorkspaceLease(Base):
    id: UUID
    workspace_id: UUID (FK)
    holder_run_id: Optional[str]
    holder_identity: Optional[str]
    acquired_at: datetime
    expires_at: datetime
    released_at: Optional[datetime]
    version: int  # Optimistic locking
```

#### RunSession

**Table:** `run_sessions`  
**Purpose:** Persistent record of run execution.

```python
class RunSession(Base):
    id: UUID
    workspace_id: UUID (FK)
    run_id: str (unique)
    parent_run_id: Optional[str]
    state: RunSessionState
    principal_id: Optional[str]
    sandbox_id: Optional[UUID] (FK)
    checkpoint_id: Optional[UUID] (FK)
    request_payload_json: Optional[str]
    result_payload_json: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
```

---

### Checkpoint Entities

#### WorkspaceCheckpoint

**Table:** `workspace_checkpoints`  
**Purpose:** Workspace state snapshot metadata.

```python
class WorkspaceCheckpoint(Base):
    id: UUID
    workspace_id: UUID (FK)
    checkpoint_id: str (unique)
    version: str
    storage_key: str  # S3 object key
    storage_size_bytes: Optional[int]
    state: CheckpointState
    manifest_json: Optional[str]
    created_by_run_id: Optional[str]
    previous_checkpoint_id: Optional[UUID] (self-FK)
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

#### WorkspaceActiveCheckpoint

**Table:** `workspace_active_checkpoints`  
**Purpose:** Points to current checkpoint for restore.

```python
class WorkspaceActiveCheckpoint(Base):
    id: UUID
    workspace_id: UUID (unique, FK)
    checkpoint_id: UUID (FK)
    changed_by: Optional[str]
    changed_reason: Optional[str]
```

---

### Event Entities

#### RuntimeEvent

**Table:** `runtime_events`  
**Purpose:** Append-only event log for runs.

```python
class RuntimeEvent(Base):
    id: UUID
    run_session_id: UUID (FK)
    event_type: RuntimeEventType
    actor_id: Optional[str]
    actor_type: Optional[str]
    payload_json: Optional[str]
    occurred_at: datetime
    correlation_id: Optional[str]
```

#### AuditEvent

**Table:** `audit_events`  
**Purpose:** Security audit log.

```python
class AuditEvent(Base):
    id: UUID
    category: AuditEventCategory
    actor_id: Optional[str]
    actor_type: Optional[str]
    resource_type: str
    resource_id: str
    action: str
    outcome: str  # "success", "failure", "denied"
    payload_json: Optional[str]
    workspace_id: Optional[UUID] (FK)
    occurred_at: datetime
    immutable: bool  # Always True
```

---

## Providers

### SandboxProvider (Protocol)

**File:** `src/infrastructure/sandbox/providers/base.py`  
**Lines:** ~356

**Abstract Methods:**

| Method | Purpose |
|--------|---------|
| `get_active_sandbox()` | Get active sandbox for workspace |
| `provision_sandbox()` | Create new sandbox |
| `get_health()` | Check sandbox health |
| `stop_sandbox()` | Terminate sandbox |
| `attach_workspace()` | Attach workspace to sandbox |
| `update_activity()` | Update last activity timestamp |

**Data Types:**

```python
@dataclass
class SandboxInfo:
    ref: SandboxRef
    state: SandboxState
    health: SandboxHealth
    workspace_id: Optional[UUID]
    last_activity_at: Optional[datetime]
    error_message: Optional[str]
```

---

### Daytona Provider

**File:** `src/infrastructure/sandbox/providers/daytona.py`  
**Lines:** ~694  
**Purpose:** Production provider using Daytona Cloud/BYOC.

**Key Features:**
- Daytona SDK v2 integration
- Snapshot-based provisioning
- Auto-stop configuration
- Volume mounting for agent packs

**Configuration:**
- `DAYTONA_API_KEY` - Authentication
- `DAYTONA_API_URL` - Self-hosted URL (optional)
- `DAYTONA_TARGET` - Region (default: "us")
- `DAYTONA_BASE_IMAGE` - Base Docker image
- `DAYTONA_SANDBOX_SNAPSHOT_NAME` - Snapshot name

---

### Local Compose Provider

**File:** `src/infrastructure/sandbox/providers/local_compose.py`  
**Lines:** ~400  
**Purpose:** Development provider using Docker Compose.

**Key Features:**
- Local Docker Compose integration
- No gateway support (for dev only)
- Fast startup
- Minimal resource usage

**Limitations:**
- No ZeroClaw gateway (cannot execute runs)
- Single node only
- No checkpoint support

**Use Case:**
Development and testing of workspace/routing logic without Daytona dependency.

---

### Provider Factory

**File:** `src/infrastructure/sandbox/providers/factory.py`  
**Lines:** ~200

```python
def get_provider(profile: Optional[str] = None) -> SandboxProvider:
    """Factory function to get configured provider."""
    profile = profile or settings.SANDBOX_PROFILE
    
    if profile == "daytona":
        return DaytonaProvider()
    elif profile == "local_compose":
        return LocalComposeProvider()
    else:
        raise SandboxProfileError(f"Unknown profile: {profile}")
```

---

## API Routes

### Business Routes (`/api/v1/*`)

#### runs.py

**Prefix:** `/api/v1/runs`  
**Lines:** ~470

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /` | start_run | Execute run with routing |

**Request:**
```json
{
  "agent_pack_id": "optional-pack-uuid",
  "input": {"message": "Hello"},
  "requested_egress_urls": [],
  "requested_tools": [],
  "allowed_hosts": ["api.example.com"],
  "allowed_tools": ["read_file"],
  "allowed_secrets": ["API_KEY"],
  "secrets": {"API_KEY": "secret-value"}
}
```

**Response:**
```json
{
  "run_id": "run-uuid",
  "status": "success",
  "is_guest": false,
  "message": "Run completed",
  "injected_secrets": ["API_KEY"],
  "output": "Assistant response",
  "bridge_output": {...}
}
```

---

#### workspaces.py

**Prefix:** `/api/v1/workspaces`  
**Lines:** ~350

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /` | list_workspaces | List user's workspaces |
| `POST /` | create_workspace | Create new workspace |
| `GET /{id}` | get_workspace | Get workspace details |
| `DELETE /{id}` | delete_workspace | Delete workspace |
| `POST /{id}/checkpoints` | create_checkpoint | Create checkpoint |
| `GET /{id}/checkpoints` | list_checkpoints | List checkpoints |

---

#### agent_packs.py

**Prefix:** `/api/v1/agent-packs`  
**Lines:** ~450

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /` | list_packs | List workspace packs |
| `POST /` | create_pack | Register new pack |
| `GET /{id}` | get_pack | Get pack details |
| `POST /{id}/validate` | validate_pack | Validate pack integrity |
| `POST /{id}/deploy` | deploy_pack | Deploy to sandbox |

---

#### persistence.py

**Prefix:** `/api/v1/persistence`  
**Lines:** ~600

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /checkpoint` | create_checkpoint | Create workspace checkpoint |
| `POST /restore` | restore_checkpoint | Restore from checkpoint |
| `GET /state` | get_state | Get workspace state |
| `POST /state` | save_state | Save workspace state |

---

### OSS Routes (Root Level)

#### oss/runs.py

**Path:** `/runs`  
**Lines:** ~291

**Purpose:** End-user execution with SSE streaming.

**Headers:**
- `X-User-ID` (required) - External user identifier
- `X-Session-ID` (optional) - Session continuity
- `X-Idempotency-Key` (optional) - Idempotency

**Request:**
```json
{
  "message": "Hello, agent!"
}
```

**Response:** SSE Stream
```
event: queued
data: {"position": 1}

event: provisioning
data: {"step": "workspace_ready"}

event: running
data: {"step": "bridge_execute"}

event: message
data: {"role": "assistant", "content": "Hello!"}

event: completed
data: {"finish_reason": "stop"}
```

**Error Events:**
```
event: failed
data: {"error": "Something went wrong", "error_category": "agent_error"}
```

---

#### oss/health.py

**Path:** `/health`, `/ready`  
**Lines:** ~80

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Component health (always 200) |
| `GET /ready` | Readiness check (200 if ready, 503 if not) |

---

#### oss/metrics.py

**Path:** `/metrics`  
**Lines:** ~100

**Purpose:** Prometheus metrics endpoint.

**Metrics:**
- `minerva_runs_total` - Total runs executed
- `minerva_run_duration_seconds` - Run latency
- `minerva_sandbox_active` - Active sandboxes
- `minerva_lease_conflicts_total` - Lease conflict count
