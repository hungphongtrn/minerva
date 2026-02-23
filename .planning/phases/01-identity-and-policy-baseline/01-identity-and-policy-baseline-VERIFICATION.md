---
phase: 01-identity-and-policy-baseline
verified: 2026-02-23T14:46:35Z
status: passed
score: 6/6 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 3/6
  gaps_closed:
    - "User can read/write only resources in their own workspace and cannot access other users' workspace data."
    - "Owner/member role behavior differences are observable in API outcomes."
    - "Runtime runs enforce default-deny network egress and tool allowlists."
  gaps_remaining: []
  regressions: []
---

# Phase 1: Identity and Policy Baseline Verification Report

**Phase Goal:** Users can authenticate requests safely and execute only within authorized, policy-constrained boundaries.
**Verified:** 2026-02-23T14:46:35Z
**Status:** passed
**Re-verification:** Yes - after gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can authenticate API requests with a personal API key. | ✓ VERIFIED | `src/api/dependencies/auth.py` resolves/validates API keys through `ApiKeyService.validate_key`; protected endpoint in `src/api/routes/whoami.py`; acceptance suite `uv run pytest src/tests/integration/test_phase1_acceptance.py -q` passed (32 passed). |
| 2 | User/operator can rotate or revoke API keys and revoked keys fail subsequent requests. | ✓ VERIFIED | `src/api/routes/api_keys.py` calls `rotate_key`/`revoke_key`; `src/identity/service.py` invalidates old key material and enforces inactive rejection; acceptance tests include rotate/revoke lifecycle pass. |
| 3 | User can read/write only resources in their own workspace and cannot access other workspace data. | ✓ VERIFIED | `src/api/routes/workspace_resources.py` enforces `authorize_action` + `with_rls_context`; `src/db/rls_context.py` uses executable `SELECT set_config(..., true)`; migration `src/db/migrations/versions/0001_identity_policy_baseline.py` uses `current_setting('app.workspace_id', true)` predicates; cross-workspace tests pass in acceptance run. |
| 4 | Owner/member role behavior differences are observable in API outcomes. | ✓ VERIFIED | Membership-backed role lookup is implemented in `src/api/routes/workspace_resources.py` (`Membership` query + `get_role_from_string`) and `src/authorization/guards.py` (`get_membership_role`); role behavior tests pass in acceptance run. |
| 5 | Requests without explicit identity are assigned random guest identity and run in guest non-persistent mode. | ✓ VERIFIED | `resolve_principal_or_guest` in `src/api/dependencies/auth.py` falls back to `create_guest_principal`; `src/guest/identity.py` generates random guest IDs; `src/services/run_service.py` guest persistence guard blocks `persist_run`/`persist_checkpoint`; guest acceptance tests pass. |
| 6 | Runtime policy enforces default-deny egress/tool controls and scoped secrets. | ✓ VERIFIED | `src/services/run_service.py` now enforces egress/tool checks in `execute_run` (loops over `requested_egress_urls` and `requested_tools`) and returns deterministic denied results; route `src/api/routes/runs.py` maps denied results to 403; default-deny egress/tool/secret tests pass in acceptance suite and service regression tests. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/api/dependencies/auth.py` | API key + guest principal resolution | ✓ VERIFIED | Exists, substantive, and wired through route dependencies. |
| `src/identity/service.py` | Key lifecycle and validation logic | ✓ VERIFIED | Exists, substantive implementation for create/validate/rotate/revoke/list/get. |
| `src/api/routes/api_keys.py` | Key lifecycle HTTP endpoints | ✓ VERIFIED | Exists, substantive endpoint surface, wired to auth and service methods. |
| `src/api/routes/workspace_resources.py` | Workspace-scoped CRUD + role-aware authz | ✓ VERIFIED | Exists, substantive CRUD and membership role resolution; no role stub remains. |
| `src/authorization/guards.py` | Membership-backed auth principal guards | ✓ VERIFIED | Exists, substantive, resolves role from `memberships` table and denies missing membership. |
| `src/db/rls_context.py` | Transaction-scoped RLS context setter | ✓ VERIFIED | Exists, substantive `set_config`-based implementation, dialect-aware guard present. |
| `src/db/migrations/versions/0001_identity_policy_baseline.py` | Real tenant RLS predicates | ✓ VERIFIED | Exists, substantive policies using `current_setting` + `WITH CHECK`; no allow-all predicates. |
| `src/services/run_service.py` | Runtime execution with policy gates | ✓ VERIFIED | Exists, substantive enforcement calls for egress/tools and scoped secret injection. |
| `src/runtime_policy/enforcer.py` | Default-deny enforcement API | ✓ VERIFIED | Exists, substantive `authorize_*` methods and filtered secrets helper. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `src/main.py` | `src/api/router.py` | `app.include_router(api_router)` | ✓ WIRED | API router is included in app startup. |
| `src/api/dependencies/auth.py` | `src/identity/service.py` | `ApiKeyService.validate_key` | ✓ WIRED | Auth dependency delegates key validation to service. |
| `src/api/routes/api_keys.py` | `src/identity/service.py` | create/rotate/revoke/list/get calls | ✓ WIRED | Endpoints invoke lifecycle methods directly. |
| `src/api/routes/workspace_resources.py` | `src/db/models.py` (`Membership`) | membership query in `_resolve_auth_principal_with_role` | ✓ WIRED | Role is resolved from DB membership, not hardcoded. |
| `src/api/routes/workspace_resources.py` | `src/authorization/policy.py` | `authorize_action(...)` | ✓ WIRED | All CRUD handlers enforce policy checks. |
| `src/api/routes/workspace_resources.py` | `src/db/rls_context.py` | `with_rls_context(...)` | ✓ WIRED | Resource queries/writes execute under explicit RLS context. |
| `src/db/rls_context.py` | `src/db/migrations/versions/0001_identity_policy_baseline.py` | `app.workspace_id/app.user_id/app.role` + `current_setting()` coupling | ✓ WIRED | Runtime context keys align with migration predicates. |
| `src/services/run_service.py` | `src/runtime_policy/enforcer.py` | `authorize_egress`/`authorize_tool` and secret filtering | ✓ WIRED | Active execution path now invokes policy hooks before success. |
| `src/api/routes/runs.py` | `src/services/run_service.py` | `start_run` + `execute_run` | ✓ WIRED | Route passes intent + policies into service and returns structured denials. |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
| --- | --- | --- |
| AUTH-01 | ✓ SATISFIED | None |
| AUTH-02 | ✓ SATISFIED | None |
| AUTH-03 | ✓ SATISFIED | None |
| AUTH-05 | ✓ SATISFIED | None |
| AUTH-06 | ✓ SATISFIED | None |
| SECU-01 | ✓ SATISFIED | None |
| SECU-02 | ✓ SATISFIED | None |
| SECU-03 | ✓ SATISFIED | None |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/api/routes/whoami.py` | 118 | TODO in `/whoami/guest` placeholder endpoint | ⚠ Warning | Auxiliary endpoint remains placeholder; does not block Phase 1 goal because run guest flow is implemented and verified elsewhere. |
| `src/api/routes/runs.py` | 224 | `status: not_implemented` in `get_run` | ℹ Info | Run retrieval is incomplete but does not block auth/policy-constrained execution goal for Phase 1. |

### Gaps Summary

All previously failed must-haves are now closed in code and wiring. Re-verification found no remaining blockers for Phase 1 goal achievement. Authentication, workspace isolation, membership-backed role behavior, guest fallback, and default-deny runtime policy enforcement are all implemented and exercised by the current acceptance suite.

---

_Verified: 2026-02-23T14:46:35Z_
_Verifier: OpenCode (gsd-verifier)_
