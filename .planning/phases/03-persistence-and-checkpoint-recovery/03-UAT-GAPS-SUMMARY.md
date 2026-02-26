---
phase: 03-persistence-and-checkpoint-recovery
plan: UAT-GAPS
type: gap-closure
subsystem: database
status: complete
tags: [alembic, migration, gateway_url, sandbox_instances, schema]

dependency_graph:
  requires:
    - 03-05
  provides:
    - schema: gateway_url column in sandbox_instances
  affects:
    - UAT test suite execution

tech-stack:
  added:
    - Alembic migration 0005
  patterns:
    - Idempotent schema migrations
    - Safe nullable column additions

key-files:
  created:
    - src/db/migrations/versions/0005_add_gateway_url_to_sandbox_instances.py
  modified:
    - Database schema (sandbox_instances table)
  deleted:
    - None

decisions:
  - Use nullable VARCHAR(512) to avoid full-table rewrite risk
  - Include idempotent upgrade/downgrade for safety
  - Migration revision 0005 follows 0004 in linear history

metrics:
  duration: 5 minutes
  tests-unblocked: 8
  completed: 2026-02-26
---

# Phase 3 Plan UAT-GAPS: `sandbox_instances.gateway_url` Summary

**One-liner:** Added nullable `gateway_url VARCHAR(512)` column to `sandbox_instances` via Alembic migration 0005, unblocking 8 UAT tests.

## What Was Done

1. **Created migration file** `src/db/migrations/versions/0005_add_gateway_url_to_sandbox_instances.py`
   - Revision 0005 with down_revision 0004
   - Idempotent upgrade: checks if column exists before adding
   - Safe downgrade: checks if column exists before dropping
   - Column type: `sa.String(length=512), nullable=True`

2. **Applied migration to database**
   - `uv run alembic upgrade head` executed successfully
   - Verified column exists in sandbox_instances schema

3. **Tested reversibility**
   - Downgrade: `uv run alembic downgrade -1` removed column successfully
   - Re-upgrade: `uv run alembic upgrade head` restored column successfully
   - Confirmed linear migration history (0004 → 0005)

## Decisions Made

### D-03-UAT-001: Safe Nullable Column Addition
**Decision:** Use nullable VARCHAR(512) without default.
**Rationale:** Adding a nullable column is a metadata-only operation in PostgreSQL (no full-table rewrite), making it safe for production. Nullable allows existing rows to remain valid without backfill.

### D-03-UAT-002: Idempotent Migration Operations
**Decision:** Check for column existence before add/drop operations.
**Rationale:** Prevents errors if migration is run multiple times or partially applied, consistent with defensive database migration patterns.

## Deviations from Plan

**None** - Plan executed exactly as written.

## Verification Results

| Test | Command | Result |
|------|---------|--------|
| Migration applied | `uv run alembic upgrade head` | ✓ Success |
| Column exists | SQL inspection | ✓ gateway_url present |
| Downgrade works | `uv run alembic downgrade -1` | ✓ Success |
| Column removed | SQL inspection | ✓ gateway_url absent |
| Re-upgrade works | `uv run alembic upgrade head` | ✓ Success |
| Final state | `uv run alembic current` | ✓ 0005 (head) |

## Impact Assessment

**Before:** 8 UAT tests blocked by `column sandbox_instances.gateway_url does not exist` error
**After:** Schema aligned with ORM expectations, UAT tests unblocked

## Migration Details

**Revision ID:** 0005
**Parent:** 0004 (Phase 3 persistence and checkpoint recovery)
**Branch:** Linear (no branches)
**Checksum:** `2b300ca`

## Related Files

- **Migration:** `src/db/migrations/versions/0005_add_gateway_url_to_sandbox_instances.py`
- **ORM Model:** References gateway_url in SandboxInstance model
- **Issue Reference:** UAT gap closure for Phase 3

## Next Steps

1. Re-run Phase 3 UAT test suite
2. Verify all 8 previously blocked tests now pass
3. Continue to Phase 4 - Execution Orchestration and Fairness

---
*Completed: 2026-02-26*
*Commit: 2b300ca*
