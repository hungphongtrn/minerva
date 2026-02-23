# Phase 01 Plan 09: Member Workspace Resource Permission Fix Summary

**Plan ID:** 01-09  
**Phase:** 01-identity-and-policy-baseline  
**Type:** Gap Closure  
**Completion Date:** 2026-02-23  
**Duration:** ~30 minutes

## One-Liner

Closed the diagnosed UAT gap by tightening MEMBER role permissions on WORKSPACE_RESOURCE to read-only (Action.READ only), removing CREATE/UPDATE/DELETE permissions, and adding comprehensive regression coverage at policy, integration, and acceptance levels.

## What Was Delivered

### Task 1: Authorization Matrix Fix (src/authorization/policy.py)

Updated the AUTHORIZATION_MATRIX to enforce AUTH-05 role divergence:

- **MEMBER role for WORKSPACE_RESOURCE**: Now only has `Action.READ`
- **Removed permissions**: `Action.CREATE`, `Action.UPDATE`, `Action.DELETE`
- **OWNER and ADMIN roles**: Retained full mutation permissions (unchanged)

**Code change:**
```python
ResourceType.WORKSPACE_RESOURCE: {
    Action.READ,
    # Action.CREATE,  # Removed
    # Action.UPDATE,  # Removed
    # Action.DELETE,  # Removed
},
```

### Task 2: Policy-Level Regression Tests (src/tests/authorization/test_workspace_isolation.py)

Added 9 new test assertions to prevent regression:

**Matrix tests (can_perform function):**
- `test_member_cannot_create_workspace_resource`
- `test_member_cannot_update_workspace_resource`
- `test_member_cannot_delete_workspace_resource`
- `test_member_can_read_workspace_resource` (positive assertion)
- `test_owner_can_mutate_workspace_resource` (verify owner still works)
- `test_admin_can_mutate_workspace_resource` (verify admin still works)

**Path tests (authorize_action function):**
- `test_member_create_workspace_resource_denied` - verifies 403 with detail
- `test_member_update_workspace_resource_denied` - verifies 403
- `test_member_delete_workspace_resource_denied` - verifies 403

### Task 3: API-Level Tests (Integration & Acceptance)

**src/tests/integration/test_membership_role_behavior.py:**
- Fixed `test_owner_can_delete_resource_member_cannot` to expect 403 for member
- Added `test_member_cannot_create_workspace_resource` - directly tests the reported UAT scenario
- Added `test_member_cannot_update_workspace_resource` - covers PATCH endpoint

**src/tests/integration/test_phase1_acceptance.py (TestRoleBehavior):**
- Added `test_member_cannot_create_workspace_resources` - Phase 1 acceptance criterion demonstrating role divergence

## Test Results

| Test Suite | Tests | Result |
|------------|-------|--------|
| Unit: test_workspace_isolation.py | 60 passed | ✓ |
| Integration: test_membership_role_behavior.py | 5 passed | ✓ |
| Acceptance: test_phase1_acceptance.py -k RoleBehavior | 5 passed | ✓ |

**Total new tests added:** 13 (9 policy-level + 4 API-level)

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01-09-001 | Remove all mutation permissions (CREATE/UPDATE/DELETE) from MEMBER role on WORKSPACE_RESOURCE | AUTH-05 requires deterministic, observable role divergence; member permissions violated this requirement |
| D-01-09-002 | Add both positive and negative assertions in tests | Ensures tests fail if permissions are accidentally reintroduced or if owner/admin permissions regress |
| D-01-09-003 | Include explicit UAT scenario test | `test_member_cannot_create_workspace_resource` directly covers the reported issue: "Member POST /workspaces/{workspace_id}/resources returned 201; expected 403" |

## Deviation from Plan

None - plan executed exactly as written. All three tasks completed:
1. ✓ Policy matrix tightened
2. ✓ Regression tests added
3. ✓ Integration/acceptance tests updated

## Gap Closure Verification

✅ **UAT Gap 4 (Test 4: Membership-backed role behavior) - CLOSED**

**Before fix:**
- Member POST /workspaces/{workspace_id}/resources returned 201 Created
- No observable difference between owner/admin/member for workspace resource mutations

**After fix:**
- Member POST /workspaces/{workspace_id}/resources returns 403 Forbidden
- Member mutation attempts denied with descriptive error: "Role 'member' cannot perform 'create' on 'workspace_resource'"
- Owner and admin mutation attempts succeed with 201/204
- Deterministic role divergence now observable and tested

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/authorization/policy.py` | Modified | Tightened MEMBER permissions on WORKSPACE_RESOURCE to read-only |
| `src/tests/authorization/test_workspace_isolation.py` | Modified | Added 9 regression tests for member mutation denials |
| `src/tests/integration/test_membership_role_behavior.py` | Modified | Updated delete test, added create/update denial tests |
| `src/tests/integration/test_phase1_acceptance.py` | Modified | Added acceptance test for member create denial |

## Key Links Established

1. **src/api/routes/workspace_resources.py → src/authorization/policy.py**
   - Via: `authorize_action(Action.CREATE/UPDATE/DELETE)` calls
   - Pattern: Routes delegate to policy matrix for permission decisions

2. **src/tests/integration/test_membership_role_behavior.py → /api/v1/workspaces/{id}/resources**
   - Via: `client.post()` assertions verifying 403 response
   - Pattern: Integration tests prove API-level denial behavior

## Commits

1. `d66f658` - feat(01-09): tighten MEMBER permissions on WORKSPACE_RESOURCE to read-only
2. `3daffed` - test(01-09): add API-level tests for member mutation denials

## Next Steps

- Phase 1 now has all identified gaps closed (Gap 1 via 01-06, Gap 2 via 01-07, Gap 3 via 01-08, Gap 4 via 01-09)
- Re-run full Phase 1 verification to confirm `passed` status
- Proceed to Phase 2: Workspace Lifecycle and Agent Pack Portability

## Traceability

- **Requirement:** AUTH-05 (Owner/member roles produce different authorization outcomes)
- **UAT Test:** Test 4 - Membership-backed role behavior
- **Gap:** Member could create workspace resources (201 instead of 403)
- **Fix:** 01-09 tightens authorization matrix and adds regression coverage
- **Status:** ✅ Closed with deterministic, tested 403 behavior

---
*Generated: 2026-02-23*
*Duration: ~30 minutes*
*Commits: d66f658, 3daffed*
