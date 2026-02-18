# Python + TS Multi-User Pi Platform Design

## Objective
Build a scalable multi-user platform for pi coding agent workloads with:
- Real POSIX workspaces
- Per-workspace/session isolation
- Lease-based single-writer safety
- HOT/COLD snapshot lifecycle
- Compatibility with Kubernetes workers and serverless control-plane

## Architecture Overview
- Control plane is stateless and serverless-friendly.
- Data plane is stateful and runs long-lived workers.
- Workers scale horizontally; agents are multiplexed per worker.
- Python is the primary orchestration stack.
- TypeScript is used only where direct pi SDK integration is required.

## Section 1: Python/TS Boundary Contract (Approved)
### Decision
Use a Python supervisor that spawns a TypeScript agent-runtime subprocess per leased workspace, communicating over JSON-RPC via stdin/stdout.

### Ownership Split
- Python owns:
  - Lease lifecycle
  - Placement and worker orchestration
  - Workspace restore/snapshot/eviction lifecycle
  - State transitions and fencing enforcement at control-plane boundaries
- TypeScript runtime owns:
  - `createAgentSession()`
  - `createCodingTools(cwd)`
  - Prompt execution and event streaming
  - Tool execution inside workspace-scoped cwd

### RPC Contract
Each request includes `workspace_id` and `lease_token`.
Methods:
- `start_session`
- `prompt`
- `heartbeat`
- `stop_session`
- `health`

Any stale `lease_token` returns fenced error (`LEASE_FENCED` semantics).

## Section 2: Stack by Layer (Approved)
### Control Plane
- Python `FastAPI` + `Uvicorn`
- `Pydantic v2`
- `SQLAlchemy 2.0` + `Alembic`
- PostgreSQL for leases/workspaces/workers/snapshots metadata
- Optional event fanout later via Redis/NATS (not required for MVP)

### Worker Supervisor
- Python `asyncio` service
- Manages per-workspace TS subprocess lifecycle
- Performs restore, heartbeat forwarding, idle tracking, and eviction

### pi SDK Runtime
- Node.js 20 + TypeScript runtime package
- Wraps `@mariozechner/pi-coding-agent`
- Exposes JSON-RPC over stdio

### Storage
- HOT: local POSIX disk, sharded workspace paths
- COLD: S3-compatible object storage (MinIO/S3/GCS API)
- Archive format: `tar.zst` with manifest + version

### Tooling
- Python workflows use `uv`
- TS runtime built in isolated subfolder under `src/`
- Local dev via Docker Compose (Postgres + MinIO)

## Section 3: Data Model + Minimal APIs (Approved)
### Core Tables
`workspaces`
- `workspace_id` (pk)
- `state` (`COLD|RESTORING|HOT|SNAPSHOTTING`)
- `current_worker_id`
- `current_lease_token`
- `last_activity_at`
- `snapshot_version`
- `updated_at`

`leases`
- `workspace_id` (pk/fk)
- `lease_token`
- `worker_id`
- `expires_at`
- `heartbeat_at`
- `version`
- `updated_at`

`workers`
- `worker_id` (pk)
- `status`
- `active_agents`
- `capacity_agents`
- `last_heartbeat_at`
- `labels_json`

`snapshots`
- `workspace_id`
- `version`
- `object_key`
- `size_bytes`
- `checksum`
- `created_at`
- `manifest_json`

### Invariants
1. One active lease per workspace.
2. All mutating operations require current `lease_token`.
3. State transitions restricted to:
   - `COLD -> RESTORING -> HOT -> SNAPSHOTTING -> COLD`

### Minimal Control Plane APIs
- `POST /v1/workspaces/{id}/acquire`
- `POST /v1/workspaces/{id}/heartbeat`
- `POST /v1/workspaces/{id}/release`
- `POST /v1/workspaces/{id}/activity`
- `GET /v1/workspaces/{id}`

### Worker Internal Ops
- `ensure_hot(workspace_id, lease_token)`
- `prompt(workspace_id, lease_token, prompt)`
- `stop_and_snapshot(workspace_id, lease_token)`

## Section 4: Failure Handling + Verification (Approved)
### Failure Handling
- Worker crash: lease expiry enables safe steal + reassignment.
- Split-brain defense: fenced stale token cannot mutate.
- Snapshot failure: remain HOT, enqueue retry.
- Restore failure: keep non-HOT state with bounded retries.
- Control-plane restart: recover from DB as source of truth.

### Verification by Phase
- Phase 1 (MVP): lease/state unit tests, snapshot roundtrip, Python<->TS runtime integration.
- Phase 2 (multi-worker): placement/load tests, crash + lease-steal recovery tests.
- Phase 3 (k8s readiness): API contract tests + workload tests.
- Phase 4 (hardening): quotas, traversal/path safety, isolation checks.

## Additional Scenario 5 (Approved)
### Business Profile Swap Test (On-Demand E2E)
Purpose: verify domain behavior can be changed by profile content (`AGENTS.md` + skills) without platform code changes.

Profile example: Travel Desk / Flight Booking assistant.

Assertions:
1. Core lease/workspace invariants remain unchanged.
2. Profile-specific behavior is enforced (policy + output schema).
3. Switching profile requires no control-plane/worker implementation changes.
4. Reverting profile restores baseline behavior.

Execution policy:
- On-demand e2e suite only.
- Excluded from default CI pipeline.
- Invoked via explicit e2e command/tag.

## Open Decisions Deferred to Planning
- Exact isolation mode default (process vs container-per-agent)
- Placement policy tie-break strategy (pure least-load vs affinity hash)
- Exact heartbeat/TTL defaults per environment tier
- Snapshot retry and backoff policy constants

## Next Step
Use `writing-plans` skill to produce a concrete implementation plan and task breakdown from this approved design.
