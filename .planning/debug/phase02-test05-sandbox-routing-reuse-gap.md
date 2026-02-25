---
status: diagnosed
trigger: "Investigate UAT gap from Phase 02 Test 5: Active healthy sandbox is reused for routing when available"
created: "2026-02-25T00:00:00Z"
updated: "2026-02-25T00:00:00Z"
---

## Investigation Summary

**Problem:** Back-to-back resolve calls for the same workspace returned different sandbox_id values instead of reusing an existing active healthy sandbox.

**Root Cause:** Missing database transaction commit in the sandbox provisioning flow.

## Current Focus

hypothesis: Database session is not committed after provisioning, causing sandboxes to be invisible to subsequent requests
test: Traced code flow from API route through orchestrator to repository layer
expecting: Found that repository methods use session.flush() but never commit
next_action: Document artifacts and required fixes

## Symptoms

expected: POST /workspaces/{id}/sandbox/resolve returns an existing healthy sandbox when one exists; response includes sandbox state (READY) and routing info
actual: Back-to-back resolve calls for the same workspace returned different sandbox_id values within seconds instead of routing to an existing active healthy sandbox
errors: No explicit error - silent failure to persist sandbox records
reproduction: Make two consecutive resolve calls for the same workspace within seconds
started: Issue discovered during Phase 02 UAT testing

## Eliminated

- hypothesis: State mismatch between provider and database (READY vs ACTIVE)
  evidence: Orchestrator correctly maps provider state to database state (line 361 sets ACTIVE)
  timestamp: 2026-02-25T00:00:00Z

- hypothesis: Race condition in concurrent requests
  evidence: Issue occurs in back-to-back sequential calls, not just concurrent
  timestamp: 2026-02-25T00:00:00Z

- hypothesis: Query filter logic error
  evidence: Repository query correctly filters by ACTIVE state and HEALTHY status
  timestamp: 2026-02-25T00:00:00Z

## Evidence

- timestamp: 2026-02-25T00:00:00Z
  checked: src/api/routes/workspaces.py resolve_sandbox endpoint
  found: No explicit db.commit() call after lifecycle resolution
  implication: Changes are not persisted before session closes

- timestamp: 2026-02-25T00:00:00Z
  checked: src/services/sandbox_orchestrator_service.py resolve_sandbox flow
  found: Orchestrator calls repository methods that only flush, orchestrator never commits
  implication: Sandbox records created but not committed to database

- timestamp: 2026-02-25T00:00:00Z
  checked: src/db/repositories/sandbox_instance_repository.py
  found: All update methods use session.flush() but never session.commit()
  implication: Repository layer assumes caller will commit, but caller doesn't

- timestamp: 2026-02-25T00:00:00Z
  checked: src/db/session.py get_db() dependency
  found: Session is created with autocommit=False, no middleware or hook to auto-commit
  implication: Each request's session is closed without committing changes

- timestamp: 2026-02-25T00:00:00Z
  checked: src/main.py application setup
  found: No commit middleware or event handlers registered
  implication: Application relies on explicit commits in route handlers

- timestamp: 2026-02-25T00:00:00Z
  checked: src/tests/integration/conftest.py
  found: Test client override DOES commit on successful requests (line 81)
  implication: Tests pass because of override, production fails because no override

## Resolution

root cause: "Database transaction commit is missing in the sandbox resolution flow. The orchestrator creates sandbox records via repository methods (which only flush to DB), but neither the orchestrator nor the API route commits the transaction. When the request ends, the session closes and uncommitted changes are discarded. Subsequent requests see no existing sandbox and provision new ones."

fix: "Add explicit db.commit() in the resolve_sandbox endpoint after successful lifecycle resolution, or add commit handling in the orchestrator's resolve_sandbox method."

verification: "Not yet applied - research-only investigation"

files_changed: []

## Artifacts

### File: src/api/routes/workspaces.py
**Issue:** Missing `db.commit()` after lifecycle resolution
**Lines:** 260-290 (after lifecycle.resolve_target() call)
**Details:** The resolve_sandbox endpoint calls lifecycle.resolve_target() which provisions sandboxes, but the database session is never committed before the function returns. This causes all sandbox records to be discarded when the session closes.

### File: src/services/sandbox_orchestrator_service.py
**Issue:** No transaction commit after provisioning
**Lines:** 357-364 (after successful provider.provision_sandbox())
**Details:** The orchestrator updates the sandbox record state to ACTIVE and health to HEALTHY after provisioning, but relies on the caller to commit. The repository methods only call session.flush().

### File: src/db/repositories/sandbox_instance_repository.py
**Issue:** Repository uses flush() but assumes caller commits
**Lines:** 64, 251, 275, 297, 322 (all update methods)
**Details:** All repository methods call `self._session.flush()` which writes to DB but doesn't commit the transaction. This is correct for repository pattern, but callers must commit.

### File: src/db/session.py
**Issue:** get_db() dependency doesn't auto-commit
**Lines:** 45-52
**Details:** Session is created with autocommit=False and closed in finally block without committing. This is standard practice, but routes must explicitly commit.

## Missing Fixes Required

1. **Add commit in resolve_sandbox endpoint** (src/api/routes/workspaces.py:274-290)
   - Add `db.commit()` after successful lifecycle resolution before returning response
   - Should be added after line 274 (after checking target.error)

2. **Add commit handling in orchestrator** (optional alternative)
   - Add `self._session.commit()` in resolve_sandbox method after successful provisioning
   - Lines 357-372 after setting provider_ref and updating state

3. **Add transaction boundary tests** (src/tests/integration/)
   - Test that back-to-back resolve calls return same sandbox_id
   - Verify database state persists between requests

4. **Review other endpoints for same pattern** (src/api/routes/)
   - Check workspace_resources.py (lines 232, 359, 419 have commits - good example)
   - Check agent_packs.py, runs.py for missing commits
   - Consider adding commit middleware for consistency

## Debug Session Path

**Suggested path:** `.planning/debug/phase02-test05-sandbox-routing-reuse-gap.md`

This aligns with other Phase 02 debug sessions and clearly identifies the specific test gap.
