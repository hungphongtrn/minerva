---
phase: "01-identity-and-policy-baseline"
plan: "04"
subsystem: "authz"
tags:
  - "guest"
  - "runtime-policy"
  - "default-deny"
  - "secrets"
  - "egress"
  - "authorization"
dependencies:
  requires:
    - "01-01"
    - "01-02"
  provides:
    - "guest-principal-fallback"
    - "runtime-policy-engine"
    - "scoped-secret-injection"
  affects:
    - "01-05"
tech-stack:
  added:
    - "pydantic-dataclasses"
  patterns:
    - "default-deny-authorization"
    - "dependency-injection"
    - "factory-pattern"
    - "type-safe-principals"
file-manifest:
  created:
    - "src/guest/__init__.py"
    - "src/guest/identity.py"
    - "src/runtime_policy/__init__.py"
    - "src/runtime_policy/models.py"
    - "src/runtime_policy/engine.py"
    - "src/runtime_policy/enforcer.py"
    - "src/services/__init__.py"
    - "src/services/run_service.py"
    - "src/api/routes/runs.py"
    - "src/tests/runtime_policy/__init__.py"
    - "src/tests/runtime_policy/test_guest_and_runtime_policy.py"
  modified:
    - "src/api/dependencies/auth.py"
decisions:
  - id: "D-01-04-001"
    scope: "plan"
    description: "Use cryptographically strong random IDs for guest principals using secrets.token_urlsafe"
  - id: "D-01-04-002"
    scope: "plan"
    description: "Guest principals are dataclasses with frozen=True for immutability and safety"
  - id: "D-01-04-003"
    scope: "plan"
    description: "Runtime policy engine implements pure functions with default-deny semantics"
  - id: "D-01-04-004"
    scope: "plan"
    description: "Enforcer methods raise PolicyViolationError instead of returning bool for fail-fast behavior"
  - id: "D-01-04-005"
    scope: "plan"
    description: "Wildcard subdomain matching (e.g., *.example.com) supported in egress policy"
  - id: "D-01-04-006"
    scope: "plan"
    description: "Guest persistence guard uses PermissionError with descriptive message for clarity"
metrics:
  duration: "43m"
  started: "2026-02-23"
  completed: "2026-02-23"
  commits: 6
---

# Phase 1 Plan 4: Guest Identity and Runtime Policy Summary

**One-liner:** Implemented guest principal fallback and default-deny runtime policy gates for egress, tool usage, and secrets.

## What Was Built

### Guest Identity System
- **GuestPrincipal**: Dataclass with cryptographically strong random IDs
- **create_guest_principal()**: Factory function generating unique ephemeral identities
- **is_guest_principal()**: Helper to distinguish guest from authenticated principals
- **resolve_principal_or_guest()**: Auth dependency that falls back to guest when no API key provided
- **require_non_guest()**: Dependency factory to block guest access for sensitive operations

### Runtime Policy Engine
- **PolicyDecision**: Immutable result type with allowed/reason fields
- **RuntimePolicyEngine**: Pure functions for evaluating:
  - Egress URLs against host allowlists (with wildcard support)
  - Tool IDs against tool allowlists
  - Secret names against secret allowlists
- **Default-deny**: All actions denied unless explicitly allowed

### Runtime Enforcer
- **RuntimeEnforcer**: Enforcement layer that raises on policy violations
- **authorize_egress()**: Raises PolicyViolationError for blocked URLs
- **authorize_tool()**: Raises PolicyViolationError for blocked tools
- **authorize_secret()**: Raises PolicyViolationError for blocked secrets
- **get_allowed_secrets()**: Filters secrets dictionary by policy

### Run Execution Service
- **RunService**: Orchestrates run execution with policy integration
- **RunContext**: Captures run state including guest flag
- **Guest persistence guard**: Blocks persist_run() and persist_checkpoint() for guests
- **Secret injection**: Only explicitly allowed secrets injected into run context

### API Endpoints
- **POST /runs**: Start run with policy configuration and guest mode support
- **GET /runs/{run_id}**: Get run status (notes guest runs are ephemeral)

## Test Coverage

Comprehensive test suite covering:
- Guest principal generation and uniqueness
- Auth dependency guest fallback behavior
- Invalid/revoked key handling (still raises 401, doesn't fall back to guest)
- Policy engine default-deny behavior
- Egress URL matching (exact and wildcard)
- Tool authorization
- Secret scoping and filtering
- Guest persistence restrictions
- Integration flows
- Error message contracts

**Test count:** 37 tests covering AUTH-06, SECU-01, SECU-02, SECU-03

## Requirements Mapped

| Requirement | Implementation |
|-------------|----------------|
| AUTH-06 (Guest mode) | GuestPrincipal, resolve_principal_or_guest(), guest persistence guards |
| SECU-01 (Default-deny egress) | RuntimePolicyEngine.evaluate_egress(), authorize_egress() |
| SECU-02 (Default-deny tools) | RuntimePolicyEngine.evaluate_tool(), authorize_tool() |
| SECU-03 (Scoped secrets) | RuntimePolicyEngine.evaluate_secret(), get_allowed_secrets() |

## Key Design Decisions

1. **Guest IDs are cryptographically strong**: Using `secrets.token_urlsafe(24)` for 32+ character random IDs

2. **Immutable principals**: GuestPrincipal is frozen to prevent accidental mutation

3. **Fail-fast enforcement**: Enforcer raises exceptions rather than returning bools, preventing bypass bugs

4. **Wildcard support**: Egress policy supports `*.example.com` patterns for subdomain matching

5. **Clear error messages**: PolicyViolationError includes action, resource, and reason for debugging

## Deviations from Plan

None - plan executed exactly as written.

## Dependencies on Previous Plans

- **01-01**: Database foundation, Principal type
- **01-02**: API key authentication, resolve_principal dependency

## Files Created/Modified

**Created (11 files):**
```
src/guest/__init__.py
src/guest/identity.py
src/runtime_policy/__init__.py
src/runtime_policy/models.py
src/runtime_policy/engine.py
src/runtime_policy/enforcer.py
src/services/__init__.py
src/services/run_service.py
src/api/routes/runs.py
src/tests/runtime_policy/__init__.py
src/tests/runtime_policy/test_guest_and_runtime_policy.py
```

**Modified (1 file):**
```
src/api/dependencies/auth.py
```

## Commits

1. `742ddcd` - feat(01-04): add guest identity fallback with ephemeral principal generation
2. `fbfa0c4` - feat(01-04): implement default-deny runtime policy engine and enforcement hooks
3. `2b0ab6d` - feat(01-04): wire run API flow with guest persistence guard and scoped secrets
4. `17c0c34` - fix(01-04): refactor authorization guards to factory pattern
5. `8dfc701` - fix(01-04): remove unused import from workspace_resources.py

## Next Steps

Phase 1 Plans 01-03 and 01-04 complete. Ready for Phase 1 acceptance tests.

## Traceability

- AUTH-06: Guest mode with ephemeral identities
- SECU-01: Default-deny egress control
- SECU-02: Default-deny tool control  
- SECU-03: Scoped secret injection
