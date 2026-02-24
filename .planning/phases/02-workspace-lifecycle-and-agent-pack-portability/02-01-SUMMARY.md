# Phase 02 Plan 01: Workspace Lifecycle and Agent Pack Foundation Summary

**Completed:** 2026-02-24  
**Duration:** ~30 minutes  
**Tasks:** 3/3 completed  
**Commits:** 3

---

## What Was Built

Created the Phase 2 persistence foundation for workspace lifecycle, sandbox state, and path-linked agent packs. This provides durable storage and query primitives needed for lease serialization and health-aware sandbox routing.

### New Database Entities

1. **WorkspaceLease** (`workspace_leases` table)  
   - UUID PK, workspace-scoped FK, timestamps  
   - Lease holder identification (run_id, identity)  
   - `acquired_at`, `expires_at`, `released_at` for TTL management  
   - Optimistic locking via `version` field  
   - Unique partial index prevents duplicate active lease per workspace

2. **SandboxInstance** (`sandbox_instances` table)  
   - UUID PK, workspace-scoped FK, optional agent_pack FK  
   - `profile` enum: `local_compose` | `daytona`  
   - `state` enum: pending → creating → active → unhealthy/stopping/stopped  
   - `health_status` enum: healthy | unhealthy | unknown  
   - Activity tracking: `last_activity_at`, `last_health_at`  
   - Idle TTL: `idle_ttl_seconds` for auto-stop enforcement  

3. **AgentPack** (`agent_packs` table)  
   - UUID PK, workspace-scoped FK  
   - Path-linked registration: `source_path` (folder is source of truth)  
   - `source_digest` for stale detection  
   - `validation_status` enum: pending | valid | invalid | stale  
   - `validation_report_json` for structured checklists  
   - Unique constraint on `(workspace_id, source_path)` prevents duplicate registration

4. **AgentPackRevision** (`agent_pack_revisions` table)  
   - UUID PK, agent_pack FK  
   - `source_digest` at detection time  
   - `change_summary_json` for audit trail

### Alembic Migration (0003)

- Creates all 4 tables with proper foreign keys and cascade rules
- Adds PostgreSQL enums for states, profiles, health status, validation status
- Creates routing/locking indexes:
  - `ix_sandbox_instances_workspace_state_health` for routing queries
  - `ix_workspace_leases_active_unique` partial unique index for lease safety
  - `ix_agent_packs_workspace_source_path` for registration uniqueness
- Full upgrade/downgrade tested and verified

### Repository Modules

All repositories provide focused query methods for downstream services:

- **WorkspaceLeaseRepository**  
  - `acquire_active_lease()`: Atomic lease acquisition with conflict handling  
  - `release_lease()`: Deterministic lease release  
  - `renew_lease()`: Extend lease TTL for long-running operations  
  - `get_active_lease()`: Query active lease for workspace  

- **SandboxInstanceRepository**  
  - `create()`: Record new sandbox instance  
  - `list_active_healthy_by_workspace()`: Primary routing query  
  - `list_unhealthy_sandboxes()`: Health monitoring  
  - `list_idle_sandboxes()`: TTL enforcement worker support  
  - `update_state()`, `update_health()`, `update_activity()`: Lifecycle management

- **AgentPackRepository**  
  - `create()`: Register path-linked pack  
  - `get_by_workspace_and_path()`: Lookup by unique constraint  
  - `update_validation_status()`, `update_source_digest()`: Validation workflow  
  - `add_revision()`, `get_revisions()`: Change tracking

### Verification

- **Smoke Tests:** `src/tests/smoke/test_phase2_schema_bootstrap.py`  
  - 10 core assertions pass (tables, columns, indexes, imports)  
  - 3 PostgreSQL-specific enum tests skip on SQLite  
  - Migration chain verification confirms 0003 is head

- **Migration Test:**  
  - `alembic upgrade head` → applies 0003  
  - `alembic downgrade -1` → rolls back cleanly  
  - `alembic upgrade head` → reapplies successfully

---

## Files Created/Modified

| Path | Type | Description |
|------|------|-------------|
| `src/db/models.py` | Modified | Added 4 new model classes + enums |
| `src/db/migrations/versions/0003_workspace_lifecycle_and_agent_pack_foundation.py` | Created | Alembic migration for Phase 2 schema |
| `src/db/repositories/__init__.py` | Created | Repository module exports |
| `src/db/repositories/workspace_lease_repository.py` | Created | Lease acquisition/release/renewal queries |
| `src/db/repositories/sandbox_instance_repository.py` | Created | Sandbox routing and health queries |
| `src/db/repositories/agent_pack_repository.py` | Created | Pack registration and validation queries |
| `src/tests/smoke/conftest.py` | Created | Smoke test fixtures |
| `src/tests/smoke/test_phase2_schema_bootstrap.py` | Created | Schema validation smoke tests |

---

## Deviations from Plan

**None.** Plan executed exactly as written.

All verification criteria met:
- ✓ All four entities import successfully with minimum required fields
- ✓ Migration applies and rolls back without manual SQL edits
- ✓ Schema invariants for lease and pack uniqueness encoded in DDL
- ✓ Repositories provide callable methods for downstream services
- ✓ Smoke suite passes with Phase 2 schema baseline assertions
- ✓ Alembic can migrate to head with revision 0003 present

---

## Architecture Decisions

1. **Partial unique index for active leases:** Uses PostgreSQL partial index `WHERE released_at IS NULL` to enforce one active lease per workspace at the database level.

2. **Path-linked pack registration:** Stores `source_path` as the source of truth, with `source_digest` for stale detection. This aligns with Picoclaw's filesystem-centric model.

3. **Enum types in PostgreSQL:** Using native PostgreSQL enums for state/status columns provides better type safety and validation at the database level.

4. **Repository pattern:** Each entity has a dedicated repository module with focused query methods. This keeps query logic centralized and testable.

5. **Workspace-scoped isolation:** All new tables have `workspace_id` FK with CASCADE delete, maintaining the tenant isolation pattern from Phase 1.

---

## Commits

| Hash | Message |
|------|---------|
| `a3a5303` | feat(02-01): extend ORM with workspace lifecycle and pack entities |
| `fbe424a` | feat(02-01): add Alembic migration for workspace lifecycle and agent packs |
| `2f1b8e8` | feat(02-01): add repositories and schema smoke coverage |

---

## Next Phase Readiness

This foundation enables:

- **02-02:** Provider adapter abstraction for local compose and Daytona parity  
  - Sandbox instances can be created/tracked  
  - Routing queries (`list_active_healthy_by_workspace`) ready for integration

- **02-03:** Workspace lifecycle services for durable reuse and lease serialization  
  - Lease repository ready for `acquire`/`release` integration  
  - Sandbox repository ready for health-aware routing

- **02-04:** Template scaffold and path-linked pack registration  
  - AgentPack repository ready for registration/validation  
  - Path uniqueness constraint enforced at database level

All Phase 2 requirements (AGNT-01/02/03, WORK-01/02/03/04/05/06, SECU-05) now have durable storage primitives.
