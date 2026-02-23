---
phase: 01-identity-and-policy-baseline
verified: 2026-02-23T09:19:51Z
status: gaps_found
score: 3/6 must-haves verified
gaps:
  - truth: "User can read/write only resources in their own workspace and cannot access other users' workspace data."
    status: failed
    reason: "Workspace resource flows rely on RLS context SQL that fails at runtime and DB policies are placeholder allow-all, so tenant boundaries are not reliably enforced end to end."
    artifacts:
      - path: "src/db/rls_context.py"
        issue: "Uses `SET CONFIG` statements; integration execution fails with SQL syntax errors."
      - path: "src/db/migrations/versions/0001_identity_policy_baseline.py"
        issue: "RLS policies are `USING (true)` placeholders and do not enforce tenant predicates."
      - path: "src/tests/integration/test_phase1_acceptance.py"
        issue: "Workspace isolation acceptance tests fail in current suite run."
    missing:
      - "Executable transaction-scoped RLS context SQL for supported databases"
      - "Real tenant predicates in RLS policies using app context (workspace/user/role)"
      - "Green workspace isolation acceptance tests under supported runtime DB"
  - truth: "Owner/member role behavior differences are observable in API outcomes."
    status: failed
    reason: "Role resolution is stubbed to owner in authorization path, so API behavior does not reflect real owner/member membership."
    artifacts:
      - path: "src/api/routes/workspace_resources.py"
        issue: "`_resolve_auth_principal_with_role` hardcodes user_id and `Role.OWNER` with TODO for membership lookup."
      - path: "src/authorization/guards.py"
        issue: "`resolve_auth_principal_dep` hardcodes `Role.OWNER` placeholder."
    missing:
      - "Membership-backed role lookup from DB"
      - "Authorization principal derived from actual user/workspace membership"
      - "API tests proving owner/member divergences with real role resolution"
  - truth: "Runtime runs enforce default-deny network egress and tool allowlists."
    status: failed
    reason: "Run execution path does not invoke policy enforcement hooks for egress/tool decisions before success response."
    artifacts:
      - path: "src/services/run_service.py"
        issue: "`execute_run` filters secrets but does not call egress/tool authorization methods."
      - path: "src/tests/integration/test_phase1_acceptance.py"
        issue: "Default-deny egress/tool acceptance tests fail in current suite run."
    missing:
      - "Policy checks in run execution for requested egress targets"
      - "Policy checks in run execution for requested tools"
      - "Deterministic denial responses when allowlists are empty or missing entries"
---

# Phase 1: Identity and Policy Baseline Verification Report

**Phase Goal:** Users can authenticate requests safely and execute only within authorized, policy-constrained boundaries.
**Verified:** 2026-02-23T09:19:51Z
**Status:** gaps_found
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can authenticate API requests with a personal API key. | ✓ VERIFIED | `src/api/dependencies/auth.py` validates keys via `ApiKeyService.validate_key`; `src/api/routes/whoami.py` is protected; integration run has auth tests passing. |
| 2 | User/operator can rotate or revoke API keys and revoked keys fail subsequent requests. | ✓ VERIFIED | `src/api/routes/api_keys.py` wires rotate/revoke to service; `src/identity/service.py` invalidates rotated material and rejects inactive keys; revocation tests pass in integration run. |
| 3 | User can read/write only their own workspace resources and cannot access other workspace data. | ✗ FAILED | `uv run pytest src/tests/integration -q` shows workspace isolation failures; `src/db/rls_context.py` issues `SET CONFIG` SQL errors; migration policies are placeholder `USING (true)` in `src/db/migrations/versions/0001_identity_policy_baseline.py`. |
| 4 | Owner/member roles produce different authorization outcomes in API behavior. | ✗ FAILED | Role resolution is stubbed to owner in `src/api/routes/workspace_resources.py` and `src/authorization/guards.py`, so role outcomes are not grounded in membership data. |
| 5 | Requests without explicit identity are assigned random guest identity and run in guest non-persistent mode. | ✓ VERIFIED | `src/api/dependencies/auth.py` uses `resolve_principal_or_guest` fallback to `create_guest_principal`; `src/guest/identity.py` generates random guest IDs; `src/services/run_service.py` blocks guest persistence paths. |
| 6 | Runtime policy enforces default-deny egress/tool controls and scoped secrets. | ✗ FAILED | Secret filtering exists, but `src/services/run_service.py` execute path does not enforce egress/tool checks; integration failures include default-deny egress/tool tests. |

**Score:** 3/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/api/dependencies/auth.py` | API key + guest principal resolution | ✓ VERIFIED | Substantive and wired; includes `resolve_principal`, `resolve_principal_or_guest`, and service linkage. |
| `src/identity/service.py` | Key lifecycle and validation logic | ✓ VERIFIED | Substantive lifecycle implementation with create/validate/rotate/revoke flows. |
| `src/api/routes/api_keys.py` | Key lifecycle HTTP endpoints | ✓ VERIFIED | Endpoints wired to service and auth dependency. |
| `src/api/routes/workspace_resources.py` | Workspace-scoped resource CRUD + authz | ✗ STUB | Contains TODO role lookup and hardcoded owner principal, so role behavior is not real. |
| `src/db/rls_context.py` | Transaction-scoped RLS context setter | ⚠ PARTIAL | Substantive and imported, but emitted SQL fails in current integration execution. |
| `src/db/migrations/versions/0001_identity_policy_baseline.py` | Enforced RLS policies for tenant data | ✗ STUB | RLS enabled/forced, but policies are placeholder `USING (true)` and not tenant-constraining. |
| `src/authorization/policy.py` | Owner/member action matrix and enforcement | ✓ VERIFIED | Role matrix and `authorize_action` implemented. |
| `src/guest/identity.py` | Ephemeral guest identity generation | ✓ VERIFIED | Random guest principal generation via `secrets.token_urlsafe`. |
| `src/services/run_service.py` | Runtime execution with policy enforcement | ✗ STUB | `execute_run` does not call egress/tool policy checks before success. |
| `src/runtime_policy/enforcer.py` | Central policy enforcement API | ✓ VERIFIED | Implements authorize methods and scoped secret filtering. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `src/main.py` | `src/api/router.py` | `app.include_router(api_router)` | ✓ WIRED | Route composition present and active. |
| `src/api/dependencies/auth.py` | `src/identity/service.py` | `validate_key` call | ✓ WIRED | Auth dependency invokes service validation directly. |
| `src/api/routes/api_keys.py` | `src/identity/service.py` | create/rotate/revoke methods | ✓ WIRED | Lifecycle endpoints call corresponding service methods. |
| `src/api/routes/workspace_resources.py` | `src/authorization/policy.py` | `authorize_action` | ✓ WIRED | Route handlers invoke policy authorization checks. |
| `src/api/routes/workspace_resources.py` | `src/db/rls_context.py` | `with_rls_context(...)` | ⚠ PARTIAL | Link exists but runtime execution fails due context SQL incompatibility/error. |
| `src/db/rls_context.py` | `src/db/migrations/versions/0001_identity_policy_baseline.py` | `app.workspace_id/app.user_id/app.role` policy coupling | ✗ NOT_WIRED | Migration policies do not reference app context; all use `USING (true)`. |
| `src/api/dependencies/auth.py` | `src/guest/identity.py` | `create_guest_principal()` fallback | ✓ WIRED | Missing-key path creates guest principal. |
| `src/services/run_service.py` | `src/runtime_policy/enforcer.py` | pre-action policy gate in run execution | ✗ NOT_WIRED | Methods exist but execution flow bypasses egress/tool checks. |
| `src/api/routes/runs.py` | `src/services/run_service.py` | `start_run` and `execute_run` | ✓ WIRED | Runs endpoint uses service path for execution. |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
| --- | --- | --- |
| AUTH-01 | ✓ SATISFIED | API key auth path and tests are present and passing. |
| AUTH-02 | ✓ SATISFIED | Rotate/revoke semantics implemented and exercised. |
| AUTH-03 | ✗ BLOCKED | Workspace isolation path fails in integration execution; DB RLS policies are placeholder allow-all. |
| AUTH-05 | ✗ BLOCKED | API role resolution is hardcoded owner, not membership-backed. |
| AUTH-06 | ✓ SATISFIED | Guest fallback and guest-mode execution path exist. |
| SECU-01 | ✗ BLOCKED | Default-deny egress is not enforced in active run execute path. |
| SECU-02 | ✗ BLOCKED | Default-deny tool allowlist is not enforced in active run execute path. |
| SECU-03 | ✓ SATISFIED | Secret injection is filtered by allowlist in runtime enforcer/service. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/api/routes/workspace_resources.py` | 88 | TODO role lookup placeholder | 🛑 Blocker | Real owner/member behavior cannot be enforced. |
| `src/authorization/guards.py` | 72 | TODO + hardcoded owner principal | 🛑 Blocker | Authorization outcomes are not tied to actual memberships. |
| `src/db/migrations/versions/0001_identity_policy_baseline.py` | 203 | Placeholder RLS policy comments/`USING (true)` | 🛑 Blocker | DB-level tenant isolation not enforced by policy predicates. |
| `src/services/run_service.py` | 201 | Placeholder execution flow note | ⚠ Warning | Policy hooks are incomplete in effective run path. |
| `src/api/routes/whoami.py` | 118 | TODO guest endpoint placeholder | ⚠ Warning | Auxiliary guest introspection endpoint is not complete. |
| `src/api/routes/runs.py` | 176 | `status: not_implemented` branch in retrieval | ℹ Info | Run retrieval endpoint not complete; not core Phase 1 blocker for start/execute path. |

### Human Verification Required

Not required for status determination. Automated structural checks and integration execution already found blocking gaps.

### Gaps Summary

Phase 1 is not goal-complete. Core authentication and API key lifecycle are implemented, and guest fallback exists, but policy-constrained boundaries are incomplete in three critical areas: workspace isolation is not reliably enforced end to end (broken RLS context execution plus placeholder RLS predicates), role behavior is stubbed to owner rather than derived from memberships, and default-deny egress/tool enforcement is not invoked in the active run execution path. These gaps block achievement of the phase goal as defined in ROADMAP success criteria and mapped requirements.

---

_Verified: 2026-02-23T09:19:51Z_
_Verifier: OpenCode (gsd-verifier)_
