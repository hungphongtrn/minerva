# Phase 01 Plan 07: Membership-backed Role Resolution Summary

**Plan ID:** 01-07  
**Phase:** 01-identity-and-policy-baseline  
**Type:** Gap Closure  
**Completion Date:** 2026-02-23  
**Duration:** 1.5 hours  

## Objective

Close Gap 2 by replacing owner-role stubs with real membership-backed role resolution to satisfy AUTH-05 requirement for observable owner/member behavior differences driven by actual membership data.

## What Was Delivered

### Core Implementation

1. **API Key-to-User Binding** (Task 1)
   - Added `user_id` foreign key to `api_keys` table linking to `users.id`
   - Created migration `0002_api_key_user_binding.py` with safe backfill strategy
   - Updated `Principal` NamedTuple to include `user_id` field
   - Propagated `user_id` through key creation and validation flows
   - Updated API responses to include `user_id` in key metadata

2. **Membership-backed Role Resolution** (Task 2)
   - Implemented `get_membership_role()` helper function in guards.py
   - Updated `resolve_auth_principal_dep()` to query membership table
   - Replaced hardcoded owner stubs in `_resolve_auth_principal_with_role()`
   - Added explicit 403 responses for users without workspace membership
   - Used structured error format with action, resource, and reason fields

3. **Integration Tests for Role Divergence** (Task 3)
   - Created comprehensive test suite `test_membership_role_behavior.py`
   - Tests prove owner/member differences are observable via API
   - Tests verify non-members receive deterministic 403 responses
   - Tests validate cross-workspace access denial
   - Updated fixtures to ensure proper membership setup

### Key Files Modified

| File | Changes |
|------|---------|
| `src/db/models.py` | Added `user_id` column to `ApiKey` model |
| `src/db/migrations/versions/0002_api_key_user_binding.py` | New migration for key-to-user binding |
| `src/identity/key_material.py` | Added `user_id` to `Principal` NamedTuple |
| `src/identity/repository.py` | Updated `create()` to accept and store `user_id` |
| `src/identity/service.py` | Propagate `user_id` in key creation and validation |
| `src/api/routes/api_keys.py` | Updated responses to include `user_id` |
| `src/authorization/guards.py` | Implemented membership-backed role lookup |
| `src/api/routes/workspace_resources.py` | Removed hardcoded stubs, use real membership |
| `src/tests/integration/conftest.py` | Updated fixtures with membership support |
| `src/tests/integration/test_membership_role_behavior.py` | New integration test suite |

## Decisions Made

### D-01-07-001: Automatic Owner Membership Creation
**Decision:** Workspace fixtures automatically create owner membership records.
**Rationale:** The plan required membership-backed authorization, but existing tests didn't explicitly create membership records. Making workspace fixtures create memberships ensures all tests have consistent authorization context without requiring every test to explicitly request membership fixtures.

### D-01-07-002: Safe Migration Backfill Strategy
**Decision:** Migration backfills existing API keys by binding to workspace owner.
**Rationale:** For existing API key records, the workspace owner is the most logical user to bind keys to deterministically. This maintains backward compatibility while enabling the new membership-backed authorization.

### D-01-07-003: Explicit 403 for Missing Memberships
**Decision:** Return structured 403 responses with descriptive error details when no membership is found.
**Rationale:** Clear error messages help API consumers understand authorization failures. The structured format (error, status, action, resource, reason) enables programmatic handling while maintaining security by not revealing internal details.

## Test Results

### Unit Tests
- `test_workspace_isolation.py -k role`: 17 passed
- Authorization matrix correctly enforced for owner/admin/member roles

### Integration Tests
- `test_membership_role_behavior.py`: 5 passed
  - Owner/member divergence demonstrated
  - Non-member denial verified
  - Admin role actions confirmed
  - Cross-workspace access blocked

- `test_phase1_acceptance.py -k RoleBehavior`: 4 passed
  - Owner can create resources
  - Member can read resources
  - Role scope enforcement on keys
  - Key metadata includes scopes

### Regression Tests
- `test_phase1_acceptance.py -k ApiKeyAuth`: 9 passed
- `test_phase1_acceptance.py -k KeyRotateRevoke`: Tests passing
- All existing acceptance tests continue to pass

## Gap Closure Verification

✅ **Gap 2 Closed:** Authorization principal role is now derived from real membership records, not hardcoded owner stubs.

✅ **AUTH-05 Satisfied:** Owner and member produce different API outcomes for the same workspace resource actions (demonstrated via integration tests).

✅ **Deterministic Denial:** Requests without matching workspace membership are denied with explicit 403 responses.

## Technical Implementation Notes

### Membership Lookup Pattern
```python
def get_membership_role(db: Session, user_id: UUID, workspace_id: UUID) -> Optional[Role]:
    """Query membership table and return Role enum."""
    membership = db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    
    if membership is None:
        return None
    
    return get_role_from_string(membership.role)
```

### Principal Resolution Flow
1. API key validated → Identity Principal (workspace_id, key_id, user_id, scopes)
2. Membership lookup → Role (owner/admin/member)
3. Auth Principal created → (user_id, workspace_id, role)
4. Authorization check → Policy enforcement

### Key Design Principles
- **Fail-closed:** Missing membership = 403 Forbidden
- **Fail-explicit:** Clear error messages for debugging
- **Fail-consistent:** Same behavior across all protected routes

## Next Steps

Gap 2 is now closed. Phase 1 verification can proceed to confirm:
1. All must-haves (truths and artifacts) are satisfied
2. Integration tests prove observable behavior differences
3. No hardcoded owner stubs remain in authorization path

With Gap 2 closed and Gap 1/3 already closed via 01-06 and 01-08, Phase 1 is ready for final verification and closure.

## Commits

1. `c4637e1` - feat(01-07): bind API keys to users with membership identity
2. `b8b63a8` - feat(01-07): replace owner stubs with membership-backed role resolution
3. `051bcc0` - test(01-07): add integration tests for membership role behavior
