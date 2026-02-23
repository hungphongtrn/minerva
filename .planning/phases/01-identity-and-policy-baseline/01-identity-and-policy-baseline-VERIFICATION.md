---
phase: 01-identity-and-policy-baseline
verified: 2026-02-23T16:16:26Z
status: passed
score: 6/6 must-haves verified
---

# Phase 1: Identity and Policy Baseline Verification Report

**Phase Goal:** Users can authenticate requests safely and execute only within authorized, policy-constrained boundaries.
**Verified:** 2026-02-23T16:16:26Z
**Status:** passed
**Re-verification:** Yes - post-gap closure (01-09)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Personal API key auth works and invalid keys are rejected. | ✓ VERIFIED | Auth dependency validates key and rejects missing/invalid/revoked keys in `src/api/dependencies/auth.py:24`, `src/api/dependencies/auth.py:70`, `src/api/dependencies/auth.py:202`; service-level validation path in `src/identity/service.py:102`; protected endpoint in `src/api/routes/whoami.py:89`; acceptance run `uv run pytest src/tests/integration/test_phase1_acceptance.py -q` -> 33 passed including `TestApiKeyAuth`. |
| 2 | API key rotate/revoke lifecycle is enforced. | ✓ VERIFIED | Lifecycle endpoints call service rotate/revoke in `src/api/routes/api_keys.py:261`, `src/api/routes/api_keys.py:293`; invalidation logic in `src/identity/service.py:163`, `src/identity/service.py:206`; acceptance run includes `TestKeyRotateRevoke` and passed (33 passed). |
| 3 | Workspace isolation prevents cross-tenant data access. | ✓ VERIFIED | Route enforces workspace-bound authz + membership role + RLS context in `src/api/routes/workspace_resources.py:152`, `src/api/routes/workspace_resources.py:155`, `src/api/routes/workspace_resources.py:163`; RLS context keys set via Postgres `set_config` in `src/db/rls_context.py:119`; migration policies use `current_setting('app.workspace_id', true)` in `src/db/migrations/versions/0001_identity_policy_baseline.py:233`, `src/db/migrations/versions/0001_identity_policy_baseline.py:257`; `uv run pytest src/tests/authorization/test_workspace_isolation.py -q` -> 60 passed. |
| 4 | Owner/member role behavior is observably different and deterministic. | ✓ VERIFIED | Authorization matrix sets member read-only for workspace resources in `src/authorization/policy.py:121`; route resolves DB membership role in `src/api/routes/workspace_resources.py:95` and applies `authorize_action` per CRUD action at `src/api/routes/workspace_resources.py:213`, `src/api/routes/workspace_resources.py:325`, `src/api/routes/workspace_resources.py:391`; integration tests `uv run pytest src/tests/integration/test_membership_role_behavior.py -q` -> 5 passed; acceptance role tests passed in 33-pass acceptance suite. |
| 5 | Guest identity mode assigns random ephemeral identity and blocks persistence. | ✓ VERIFIED | Guest fallback in `resolve_principal_or_guest` at `src/api/dependencies/auth.py:157` and guest creation at `src/guest/identity.py:35` (random `token_urlsafe` guest id at `src/guest/identity.py:47`); guest persistence guard blocks run/checkpoint persistence in `src/services/run_service.py:100`, `src/services/run_service.py:122`; execute path skips persistence for guests at `src/services/run_service.py:236`; acceptance guest tests passed in 33-pass acceptance suite. |
| 6 | Runtime policy default-deny egress/tools/secrets scope is enforced. | ✓ VERIFIED | Default-deny policy engine for egress/tools/secrets in `src/runtime_policy/engine.py:35`, `src/runtime_policy/engine.py:91`, `src/runtime_policy/engine.py:124`; enforcement hooks raise denials in `src/runtime_policy/enforcer.py:44`, `src/runtime_policy/enforcer.py:61`, `src/runtime_policy/enforcer.py:78`; active run path enforces all requested egress/tools and filters secrets in `src/services/run_service.py:223`, `src/services/run_service.py:227`, `src/services/run_service.py:231`; API maps policy denials to HTTP 403 in `src/api/routes/runs.py:157`; acceptance policy tests passed in 33-pass acceptance suite. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/api/dependencies/auth.py` | Auth + guest principal resolution | ✓ VERIFIED | Exists, substantive (237 lines), wired via route dependencies (`whoami`, `runs`, `api_keys`, `workspace_resources`). |
| `src/identity/service.py` | API key validation/rotate/revoke lifecycle | ✓ VERIFIED | Exists, substantive (284 lines), called by auth dependency and API key routes. |
| `src/api/routes/api_keys.py` | Create/list/get/rotate/revoke endpoints | ✓ VERIFIED | Exists, substantive (315 lines), wired to `ApiKeyService`. |
| `src/api/routes/workspace_resources.py` | Workspace-scoped CRUD with role checks | ✓ VERIFIED | Exists, substantive (419 lines), membership-based role resolution + action-specific authorization + RLS context. |
| `src/authorization/policy.py` | Deterministic RBAC matrix (owner/admin/member) | ✓ VERIFIED | Exists, substantive (272 lines), member `WORKSPACE_RESOURCE` permissions are read-only. |
| `src/db/rls_context.py` | Transaction-scoped RLS context | ✓ VERIFIED | Exists, substantive (248 lines), sets/clears `app.workspace_id`, `app.user_id`, `app.role`. |
| `src/db/migrations/versions/0001_identity_policy_baseline.py` | Tenant isolation RLS predicates | ✓ VERIFIED | Exists, substantive (295 lines), no allow-all RLS predicates; uses `current_setting` and `WITH CHECK`. |
| `src/guest/identity.py` | Random guest principal generation | ✓ VERIFIED | Exists, substantive (70 lines), random guest IDs and `is_guest` identity contract. |
| `src/services/run_service.py` | Guest persistence guard + runtime policy enforcement | ✓ VERIFIED | Exists, substantive (266 lines), enforces egress/tool checks and scoped secret filtering in execute path. |
| `src/runtime_policy/enforcer.py` | Policy denial enforcement hooks | ✓ VERIFIED | Exists, substantive (158 lines), raises `PolicyViolationError` on denied actions. |
| `src/api/routes/runs.py` | Runtime execution endpoint + denial mapping | ✓ VERIFIED | Exists, substantive (226 lines), routes denied policy outcomes to 403 and reports guest mode state. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `src/main.py` | `src/api/router.py` | `app.include_router(api_router)` | ✓ WIRED | API routes are registered at startup (`src/main.py:20`). |
| `src/api/dependencies/auth.py` | `src/identity/service.py` | `ApiKeyService.validate_key(...)` | ✓ WIRED | Auth dependency delegates all key validation (`src/api/dependencies/auth.py:67`, `src/api/dependencies/auth.py:199`). |
| `src/api/routes/api_keys.py` | `src/identity/service.py` | create/list/get/rotate/revoke service calls | ✓ WIRED | Endpoints execute lifecycle methods directly (`src/api/routes/api_keys.py:188`, `src/api/routes/api_keys.py:270`, `src/api/routes/api_keys.py:302`). |
| `src/api/routes/workspace_resources.py` | `src/authorization/policy.py` | `authorize_action(...)` per CRUD action | ✓ WIRED | Route enforces action-specific checks for read/create/update/delete (`src/api/routes/workspace_resources.py:155`, `src/api/routes/workspace_resources.py:213`, `src/api/routes/workspace_resources.py:325`, `src/api/routes/workspace_resources.py:391`). |
| `src/api/routes/workspace_resources.py` | `src/db/models.py` (`Membership`) | role resolution query | ✓ WIRED | Role is loaded from membership table, not hardcoded (`src/api/routes/workspace_resources.py:96`). |
| `src/api/routes/workspace_resources.py` | `src/db/rls_context.py` | `with_rls_context(...)` around queries/writes | ✓ WIRED | Resource operations execute with explicit tenant context (`src/api/routes/workspace_resources.py:163`, `src/api/routes/workspace_resources.py:221`, `src/api/routes/workspace_resources.py:333`, `src/api/routes/workspace_resources.py:399`). |
| `src/db/rls_context.py` | `src/db/migrations/versions/0001_identity_policy_baseline.py` | `set_config` keys + `current_setting` predicates | ✓ WIRED | Runtime context keys match migration policy keys (`app.workspace_id`, `app.user_id`, `app.role`). |
| `src/api/routes/runs.py` | `src/services/run_service.py` | `start_run(...)` + `execute_run(...)` | ✓ WIRED | Route builds policies and passes intents into service (`src/api/routes/runs.py:132`, `src/api/routes/runs.py:141`). |
| `src/services/run_service.py` | `src/runtime_policy/enforcer.py` | `authorize_egress`, `authorize_tool`, `get_allowed_secrets` | ✓ WIRED | Execution path invokes enforcer before success (`src/services/run_service.py:224`, `src/services/run_service.py:228`, `src/services/run_service.py:231`). |
| `src/api/routes/runs.py` | HTTP 403 contract | parse denied result and raise `HTTPException(403)` | ✓ WIRED | Denied policy outcomes are surfaced as forbidden responses (`src/api/routes/runs.py:157`, `src/api/routes/runs.py:177`). |

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
| `src/api/routes/whoami.py` | 118 | TODO placeholder in `/whoami/guest` endpoint | ⚠ Warning | Non-blocking for phase goal: guest identity mode for run execution is implemented elsewhere (`resolve_principal_or_guest` + run flow). |
| `src/api/routes/runs.py` | 224 | `status: not_implemented` in `GET /runs/{run_id}` | ℹ Info | Non-blocking for phase goal: execution policy enforcement path is implemented in `POST /runs`. |
| `src/tests/identity/test_api_keys.py` | 139 | Out-of-date test contract (`create_key` called without required `user_id`) | ⚠ Warning | Verification signal reduced for this supplemental suite; primary acceptance + integration + authorization suites still validate must-haves and pass. |
| `src/tests/services/test_run_policy_enforcement.py` | 34 | Out-of-date test fixture contract (`Principal` missing required `user_id`) | ⚠ Warning | Supplemental service test file currently fails at fixture construction; phase acceptance policy tests still pass through runtime API path. |

### Gaps Summary

All six must-haves are present, substantive, and wired in the active API/runtime paths. Automated evidence from acceptance/integration/authorization suites confirms valid/invalid API key behavior, rotate/revoke enforcement, cross-workspace denial, deterministic owner-member role divergence, guest fallback with non-persistent execution semantics, and default-deny egress/tool/secret policy controls. Existing warnings are non-blocking placeholders and stale supplemental tests, not missing phase-goal functionality.

---

_Verified: 2026-02-23T16:16:26Z_
_Verifier: OpenCode (gsd-verifier)_
