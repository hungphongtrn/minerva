# Execution Flow

**Complete request flow from API to sandbox execution.**

---

## Table of Contents

1. [Overview](#overview)
2. [Standard Run Execution](#standard-run-execution)
3. [OSS Run Execution](#oss-run-execution)
4. [Sandbox Routing Flow](#sandbox-routing-flow)
5. [Gateway Execution Flow](#gateway-execution-flow)
6. [Error Handling](#error-handling)

---

## Overview

Minerva supports two execution paths:

| Path | Endpoint | Use Case |
|------|----------|----------|
| **Standard** | `POST /api/v1/runs` | Developer API with full policy control |
| **OSS** | `POST /runs` | End-user API with SSE streaming |

Both paths share core services but differ in:
- Authentication (API key vs external identity)
- Policy enforcement (explicit vs implicit)
- Response format (JSON vs SSE)
- Queue behavior (per-workspace vs per-user)

---

## Standard Run Execution

### Sequence Diagram

```mermaid
sequenceDiagram
    participant Client
    participant API as API Routes
    participant RunSvc as RunService
    participant Life as WorkspaceLifecycle
    participant Lease as LeaseService
    participant Orch as Orchestrator
    participant Gateway as GatewayService
    participant Provider as SandboxProvider
    participant Sandbox as ZeroClaw Runtime
    
    %% Step 1: Request received
    Client->>API: POST /api/v1/runs<br/>{message, policies, secrets}
    API->>API: Validate request body
    API->>API: Resolve principal (auth/guest)
    
    %% Step 2: Start execution
    API->>RunSvc: execute_with_routing(principal, policies, ...)
    
    %% Step 3: Resolve routing target
    RunSvc->>Life: resolve_target(principal)
    
    alt Guest mode
        Life-->>RunSvc: Return guest routing (no persistence)
    else Authenticated
        Life->>Life: Get or create workspace
        Life->>Lease: acquire_lease(workspace_id, run_id)
        
        alt Lease conflict
            Lease-->>Life: LeaseResult.CONFLICT
            Life-->>RunSvc: LifecycleTarget(error=conflict)
            RunSvc-->>API: RunResult(status=error, error_type=lease_conflict)
            API-->>Client: 409 Conflict
        else Lease acquired
            Lease-->>Life: LeaseResult.ACQUIRED
        end
        
        Life->>Orch: resolve_sandbox(workspace_id)
        
        %% Step 4: Sandbox routing
        Orch->>Orch: Apply TTL cleanup (stop idle)
        Orch->>Provider: get_active_sandbox(workspace_id)
        
        alt Existing healthy sandbox
            Provider-->>Orch: SandboxInfo(state=READY, health=HEALTHY)
            Orch-->>Life: SandboxRoutingResult(ROUTED_EXISTING)
        else No healthy sandbox
            Orch->>Provider: provision_sandbox(config)
            Provider->>Provider: Create sandbox
            Provider-->>Orch: SandboxInfo(state=HYDRATING)
            
            alt Hydration in progress
                Orch-->>Life: SandboxRoutingResult(queued=true)
            else Ready immediately
                Orch-->>Life: SandboxRoutingResult(PROVISIONED_NEW)
            end
        end
        
        Life-->>RunSvc: LifecycleTarget(workspace, sandbox, lease)
    end
    
    %% Step 5: Execute run
    RunSvc->>RunSvc: Create RunSession (non-guest only)
    RunSvc->>RunSvc: Enforce policies (egress, tools, secrets)
    
    %% Step 6: Gateway execution
    RunSvc->>Gateway: execute(sandbox_url, message, tokens)
    Gateway->>Sandbox: POST /execute (HTTP)
    Sandbox->>Sandbox: Process message
    Sandbox-->>Gateway: {output, events}
    Gateway-->>RunSvc: GatewayResult(success, output)
    
    %% Step 7: Finalize
    RunSvc->>RunSvc: Update RunSession state
    RunSvc->>Lease: release_lease(workspace_id, run_id)
    RunSvc-->>API: RunResult(status, outputs)
    API-->>Client: 200 OK {run_id, status, output}
```

### Detailed Flow

#### Step 1: API Request (`runs.py:start_run`)

```python
# Extract policies from request
egress_policy = EgressPolicy(allowed_hosts=request.allowed_hosts)
tool_policy = ToolPolicy(allowed_tools=request.allowed_tools)
secret_policy = SecretScope(allowed_secrets=request.allowed_secrets)

# Execute with routing
result = await service.execute_with_routing(
    principal=principal,
    session=db,
    egress_policy=egress_policy,
    tool_policy=tool_policy,
    secret_policy=secret_policy,
    secrets=request.secrets,
    input_message=input_message,
)
```

#### Step 2: Routing Resolution (`run_service.py:resolve_routing_target`)

```python
async def resolve_routing_target(self, principal, session, ...):
    # Guest mode: ephemeral routing
    if is_guest_principal(principal):
        return RunRoutingResult(success=True, sandbox_state="guest")
    
    # Authenticated: full lifecycle resolution
    lifecycle = WorkspaceLifecycleService(session)
    target = await lifecycle.resolve_target(
        principal=principal,
        auto_create=True,
        acquire_lease=True,
    )
    return self._process_routing_target(target, run_id, lifecycle)
```

#### Step 3: Workspace Lifecycle (`workspace_lifecycle_service.py:resolve_target`)

**Key operations:**
1. Resolve or create workspace for principal
2. Acquire lease (single-writer enforcement)
3. Resolve sandbox via orchestrator
4. Return complete target with workspace, lease, and sandbox

#### Step 4: Sandbox Orchestration (`sandbox_orchestrator_service.py:resolve_sandbox`)

**Algorithm:**
```
1. Apply TTL cleanup (stop idle sandboxes)
2. Find existing healthy sandbox → route to it
3. No healthy sandbox → provision exactly one new sandbox
4. If provisioning fails, fail fast (no retry loop)
```

#### Step 5: Policy Enforcement (`run_service.py:execute_run`)

```python
def execute_run(self, context, egress_policy, tool_policy, ...):
    # Check each requested egress URL
    for url in requested_egress_urls:
        self.enforcer.authorize_egress(url, egress_policy)
    
    # Check each requested tool
    for tool_id in requested_tools:
        self.enforcer.authorize_tool(tool_id, tool_policy)
    
    # Filter secrets by policy
    injected_secrets = self.enforcer.get_allowed_secrets(secrets, secret_policy)
```

#### Step 6: Gateway Execution (`run_service.py:_execute_via_gateway`)

```python
async def _execute_via_gateway(self, routing, message, ...):
    # Single-attempt execution (no nested retries)
    sandbox_url = self._get_authoritative_sandbox_url(routing)
    token_bundle = self._resolve_gateway_tokens(routing, session)
    
    gateway_service = SandboxGatewayService()
    return await gateway_service.execute(
        sandbox_url=sandbox_url,
        message=message,
        auth_token=token_bundle.current,
        session_id=session_id,
    )
```

---

## OSS Run Execution

### Key Differences from Standard Flow

| Aspect | Standard | OSS |
|--------|----------|-----|
| **Auth** | API key | External identity (X-User-ID) |
| **Endpoint** | `/api/v1/runs` | `/runs` |
| **Response** | JSON | SSE (Server-Sent Events) |
| **Queue** | Per-workspace | Per-user (OssUserQueue) |
| **Policy** | Explicit in request | Implicit (allow all) |
| **Sandbox** | Shared per workspace | Per-user isolation |

### Sequence Diagram

```mermaid
sequenceDiagram
    participant Client
    participant OSS as OSS Runs Route
    participant Queue as OssUserQueue
    participant RunSvc as RunService
    participant Event as EventBuilder
    participant Gateway as Gateway
    
    %% Step 1: Request received
    Client->>OSS: POST /runs<br/>X-User-ID: user123<br/>X-Session-ID: sess456
    
    %% Step 2: Validate and queue
    OSS->>OSS: Validate X-User-ID header
    OSS->>Event: Create event builder (run_id)
    OSS->>Client: SSE: event: queued
    
    %% Step 3: Queue execution
    OSS->>Queue: execute(user_id, idempotency_key, operation)
    
    %% Queue ensures per-user serialization
    Queue->>Queue: Acquire per-user lock
    
    %% Step 4: Execute run (same as standard)
    Queue->>RunSvc: execute_with_routing(principal, ...)
    RunSvc->>RunSvc: Route to sandbox
    RunSvc->>Gateway: Execute
    Gateway-->>RunSvc: Result
    RunSvc-->>Queue: RunResult
    
    Queue->>Queue: Release per-user lock
    Queue-->>OSS: OssQueueResult(result, was_cached)
    
    %% Step 5: Stream events
    alt Success
        OSS->>Client: SSE: event: running
        OSS->>Client: SSE: event: message (content)
        OSS->>Client: SSE: event: completed
    else Failure
        OSS->>Client: SSE: event: failed<br/>error: message
    end
    
    OSS->>Client: [Stream closed]
```

### SSE Event Flow

```mermaid
graph TD
    A[Client Request] --> B[queued]
    B --> C{Cold start?}
    C -->|Yes| D[provisioning]
    C -->|No| E[running]
    D --> E
    E --> F[message chunks...]
    F --> G{Result}
    G -->|Success| H[completed]
    G -->|Failure| I[failed]
    
    style B fill:#FFE4B5
    style E fill:#90EE90
    style H fill:#90EE90
    style I fill:#FFB6C1
```

### Event Types

| Event | Description | Payload |
|-------|-------------|---------|
| `queued` | Request queued | `{position, estimated_wait}` |
| `provisioning` | Sandbox being created | `{step, message}` |
| `running` | Execution started | `{step}` |
| `message` | Agent output chunk | `{role, content}` |
| `completed` | Execution succeeded | `{finish_reason}` |
| `failed` | Execution failed | `{error, error_category}` |

---

## Sandbox Routing Flow

### Routing Decision Tree

```mermaid
flowchart TD
    A[resolve_sandbox] --> B{Apply TTL cleanup}
    B --> C[Find existing sandboxes]
    
    C --> D{Has active sandbox?}
    D -->|Yes| E{Health check}
    D -->|No| F[Provision new]
    
    E -->|Healthy| G[Route to existing]
    E -->|Unhealthy| H[Exclude from routing]
    
    H --> I{Any healthy remaining?}
    I -->|Yes| G
    I -->|No| F
    
    F --> J[Provision sandbox]
    J --> K{Hydration needed?}
    
    K -->|Yes| L[Return queued status]
    K -->|No| M[Return ready]
    
    L --> N[Background hydration]
    N --> O[Hydration complete]
    
    G --> P[Return sandbox info]
    M --> P
    
    style G fill:#90EE90
    style L fill:#FFE4B5
    style P fill:#90EE90
```

### TTL Cleanup

Before routing, idle sandboxes are stopped:

```python
async def apply_ttl_cleanup(self, workspace_id):
    """Stop sandboxes that exceeded idle TTL."""
    idle_sandboxes = self._find_idle_sandboxes(workspace_id)
    
    for sandbox in idle_sandboxes:
        if self._is_stop_eligible(sandbox):
            await self._stop_sandbox(sandbox)
```

### Health-Aware Routing

```python
async def _route_to_existing(self, workspace_id):
    """Find healthy sandbox or return None."""
    candidates = self._repository.list_by_workspace(workspace_id)
    
    for sandbox in candidates:
        if sandbox.state != SandboxState.ACTIVE:
            continue
            
        health = await self._provider.get_health(sandbox.provider_ref)
        
        if health.health == SandboxHealth.HEALTHY:
            return sandbox
        else:
            # Mark unhealthy, will be excluded
            await self._mark_unhealthy(sandbox)
    
    return None
```

---

## Gateway Execution Flow

### ZeroClaw Gateway Protocol

```mermaid
sequenceDiagram
    participant Gateway as SandboxGatewayService
    participant Sandbox as ZeroClaw Runtime
    
    Gateway->>Gateway: Resolve sandbox URL
    Gateway->>Gateway: Get auth token
    
    alt Health check (optional)
        Gateway->>Sandbox: GET /health
        Sandbox-->>Gateway: 200 OK {status: healthy}
    end
    
    Gateway->>Sandbox: POST /execute
    Note over Gateway,Sandbox: Headers:<br/>Authorization: Bearer {token}<br/>X-Session-ID: {session_id}<br/>Content-Type: application/json
    
    Sandbox->>Sandbox: Validate token
    Sandbox->>Sandbox: Process message
    
    loop Streaming response
        Sandbox-->>Gateway: SSE: event: token<br/>data: {content}
    end
    
    Sandbox-->>Gateway: SSE: event: completed<br/>data: {finish_reason}
    
    Gateway->>Gateway: Parse events
    Gateway-->>Caller: GatewayResult(output, events)
```

### Gateway Result Types

| Type | Description | Handler |
|------|-------------|---------|
| `SUCCESS` | Execution completed | Return output |
| `AUTH_ERROR` | Token invalid/expired | Retry with refreshed token |
| `TRANSPORT_ERROR` | Network failure | Fail (no retry) |
| `UPSTREAM_ERROR` | Runtime error | Return error |
| `TIMEOUT` | Execution timeout | Return timeout error |

---

## Error Handling

### Error Categories

```mermaid
flowchart TD
    A[Error Occurs] --> B{Category}
    
    B -->|4xx Client| C[User Error]
    B -->|409 Conflict| D[Lease Conflict]
    B -->|5xx Server| E[System Error]
    B -->|Gateway| F[Runtime Error]
    
    C --> G[Return 400/403/404]
    D --> H[Return 409 with retry_after]
    E --> I[Return 503 with remediation]
    F --> J[Map to OSS event]
```

### Lease Conflict Handling

```python
# When lease acquisition fails
if lease_result.result == LeaseResult.CONFLICT:
    return RunRoutingResult(
        success=False,
        error_type=RoutingErrorType.LEASE_CONFLICT,
        error=f"Workspace {workspace_id} has active lease",
        remediation="Retry after current operation completes",
    )
```

HTTP Response:
```json
{
  "detail": {
    "error": "Workspace has active lease",
    "error_type": "lease_conflict",
    "remediation": "Retry after current operation completes",
    "lease_holder": "run_abc123"
  }
}
```

### Routing Failure Handling

| Error Type | HTTP Status | Retryable |
|------------|-------------|-----------|
| `PACK_NOT_FOUND` | 404 | No |
| `PACK_WORKSPACE_MISMATCH` | 403 | No |
| `LEASE_CONFLICT` | 409 | Yes (after delay) |
| `PROVIDER_UNAVAILABLE` | 503 | Yes |
| `SANDBOX_PROVISION_FAILED` | 503 | Yes |
| `GATEWAY_TIMEOUT` | 504 | Yes |
| `GATEWAY_AUTH_FAILED` | 502 | No |

### Deterministic Cleanup

All paths must release leases:

```python
try:
    target = await lifecycle.resolve_target(...)
    # ... execute run ...
finally:
    if target.lease_acquired:
        lifecycle.release_lease(workspace_id, run_id)
```

---

## Key Implementation Details

### 1. Single-Attempt Design

No nested retry loops that could spawn multiple sandboxes:

```python
# Correct: Single attempt
async def _execute_via_gateway(self, ...):
    result = await gateway.execute(...)  # One try
    return result  # Fail if it fails

# Wrong: Nested retries
async def _execute_via_gateway(self, ...):
    for attempt in range(3):  # Don't do this
        result = await gateway.execute(...)
```

### 2. Lease Scope

Leases are held only during routing and execution:

```
Acquire lease
→ Route to sandbox
→ Execute via gateway
→ Release lease
```

### 3. Guest Mode Isolation

Guest runs are completely ephemeral:
- No workspace persistence
- No run session record
- No lease acquisition
- Sandbox destroyed after execution

### 4. Idempotency

OSS endpoint supports idempotent requests:

```python
# Same idempotency key = same result
queue_result = await user_queue.execute(
    user_id=principal.external_user_id,
    idempotency_key=idempotency_key,  # Cached if seen before
    operation=execute_operation,
)
```
