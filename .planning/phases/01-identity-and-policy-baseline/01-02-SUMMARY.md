---
phase: "01-identity-and-policy-baseline"
plan: "02"
subsystem: "backend"
tags: ["fastapi", "authentication", "api-keys", "security", "hmac", "sha256"]
dependencies:
  requires:
    - "01-01: Identity foundation (models, database)"
  provides:
    - "API key authentication dependency"
    - "Key lifecycle endpoints (create/rotate/revoke)"
    - "Protected whoami endpoint for auth verification"
    - "40 automated tests for AUTH-01 and AUTH-02"
  affects:
    - "01-03: Tenant isolation middleware"
    - "All protected API endpoints"
tech-stack:
  added:
    - "pytest-asyncio"
  patterns:
    - "Repository pattern for API key persistence"
    - "Service layer for business logic"
    - "FastAPI dependency injection for auth"
    - "Timing-safe hash comparison with hmac.compare_digest"
    - "One-way key hashing (SHA-256)"
file-tracking:
  key-files:
    created:
      - "src/identity/__init__.py"
      - "src/identity/key_material.py"
      - "src/identity/repository.py"
      - "src/identity/service.py"
      - "src/api/dependencies/__init__.py"
      - "src/api/dependencies/auth.py"
      - "src/api/routes/__init__.py"
      - "src/api/routes/api_keys.py"
      - "src/api/routes/whoami.py"
      - "src/tests/identity/__init__.py"
      - "src/tests/identity/test_api_keys.py"
    modified:
      - "src/api/router.py"
      - "pyproject.toml"
decisions:
  - id: "D-01-02-001"
    text: "Use secrets.token_urlsafe for cryptographically secure key generation"
    rationale: "Python's secrets module provides the highest quality randomness suitable for authentication tokens"
  - id: "D-01-02-002"
    text: "Use SHA-256 hashing with hmac.compare_digest for timing-safe validation"
    rationale: "Prevents timing attacks by ensuring comparison time is independent of key correctness"
  - id: "D-01-02-003"
    text: "Store only key hashes in database, never plaintext keys"
    rationale: "Security best practice - if database is compromised, keys cannot be extracted"
  - id: "D-01-02-004"
    text: "Support both X-Api-Key header and Authorization: Bearer token formats"
    rationale: "Provides flexibility for different client implementations and API conventions"
  - id: "D-01-02-005"
    text: "Key rotation preserves key ID but changes material, invalidating old key immediately"
    rationale: "Allows tracking key lineage while ensuring security - old key stops working atomically"
  - id: "D-01-02-006"
    text: "Key revocation sets is_active=False rather than deleting records"
    rationale: "Preserves audit trail and allows recovery if needed (though we enforce no reuse)"
metrics:
  started: "2026-02-23T08:41:32Z"
  completed: "2026-02-23"
  duration: "~25 minutes"
  tests: "40 tests passing"
---

# Phase 01 Plan 02: Identity and Policy Baseline Summary

One-liner: Delivered personal API key authentication with secure key lifecycle controls (create/rotate/revoke) and 40 comprehensive automated tests.

## What Was Built

### Core Authentication Infrastructure

- **Key Material Handling** (`src/identity/key_material.py`):
  - `generate_api_key()`: Cryptographically secure key generation using `secrets.token_urlsafe(48)`
  - `verify_key()`: Timing-safe validation using `hmac.compare_digest` to prevent timing attacks
  - `KeyPair` and `Principal` named tuples for type safety
  - Support for key expiration checking

- **Repository Layer** (`src/identity/repository.py`):
  - `ApiKeyRepository`: CRUD operations for API keys
  - Hash-based key lookup (only hashes stored in database)
  - Methods: `get_by_hash`, `get_by_id`, `get_by_workspace`, `create`, `update_key_material`, `revoke`, `update_last_used`

- **Service Layer** (`src/identity/service.py`):
  - `ApiKeyService`: Business logic for authentication and lifecycle
  - Methods: `create_key`, `validate_key`, `rotate_key`, `revoke_key`, `list_keys`, `get_key`
  - Returns `ValidationResult` with principal or error information
  - Updates `last_used_at` timestamp on successful validation

### API Endpoints

- **Authentication Dependency** (`src/api/dependencies/auth.py`):
  - `resolve_principal`: Extracts and validates API key from `X-Api-Key` header or `Authorization: Bearer` token
  - `optional_principal`: Optional authentication for endpoints supporting both auth and guest access
  - `require_scopes`: Factory for scope-based permission control
  - Returns 401 for missing/invalid/revoked/expired keys

- **Key Lifecycle Routes** (`src/api/routes/api_keys.py`):
  - `POST /api/v1/api-keys`: Create new API key (returns full key once)
  - `GET /api/v1/api-keys`: List keys for workspace
  - `GET /api/v1/api-keys/{key_id}`: Get specific key details
  - `POST /api/v1/api-keys/{key_id}/rotate`: Rotate key (invalidates old immediately)
  - `POST /api/v1/api-keys/{key_id}/revoke`: Revoke key (blocks all future auth)

- **Whoami Probe** (`src/api/routes/whoami.py`):
  - `GET /api/v1/whoami`: Protected endpoint returning authenticated principal info
  - Useful for verifying API keys work and debugging auth issues
  - Returns workspace_id, key_id, scopes, is_active

### Security Features

- **Key Storage**: Only SHA-256 hashes stored, never plaintext
- **Timing Safety**: `hmac.compare_digest` prevents timing attacks
- **Atomic Rotation**: Old key invalidated immediately upon rotation
- **Immediate Revocation**: Revoked keys blocked on next request
- **Expiration Support**: Keys can have optional expiration dates
- **Scope System**: Keys can have permission scopes for fine-grained access

### Testing

- **40 Automated Tests** (`src/tests/identity/test_api_keys.py`):
  - Key material generation and validation
  - Successful authentication with active keys (AUTH-01)
  - Failure with unknown/invalid keys
  - Rotation invalidates previous key immediately (AUTH-02)
  - Revocation blocks subsequent requests (AUTH-02)
  - Expired key handling
  - FastAPI auth dependencies (async)
  - Timing attack resistance
  - Regression: revoked keys cannot pass even with cached hash

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

1. **Use `secrets.token_urlsafe` for key generation** - Highest quality cryptographically secure randomness
2. **Use `hmac.compare_digest` for validation** - Timing-safe comparison prevents timing attacks
3. **Store only hashes in database** - Security best practice, plaintext never persisted
4. **Support both header formats** - X-Api-Key for direct use, Authorization: Bearer for OAuth compatibility
5. **Key rotation preserves ID** - Allows audit trail while changing material
6. **Revocation uses is_active flag** - Preserves history, allows tracking

## Files Created/Modified

| File | Type | Purpose |
|------|------|---------|
| `src/identity/__init__.py` | Created | Identity module exports |
| `src/identity/key_material.py` | Created | Secure key generation and validation |
| `src/identity/repository.py` | Created | API key database operations |
| `src/identity/service.py` | Created | Authentication business logic |
| `src/api/dependencies/__init__.py` | Created | Dependencies module exports |
| `src/api/dependencies/auth.py` | Created | FastAPI auth dependencies |
| `src/api/routes/__init__.py` | Created | Routes module exports |
| `src/api/routes/api_keys.py` | Created | Key lifecycle endpoints |
| `src/api/routes/whoami.py` | Created | Authentication probe endpoint |
| `src/tests/identity/__init__.py` | Created | Test module init |
| `src/tests/identity/test_api_keys.py` | Created | 40 automated tests |
| `src/api/router.py` | Modified | Wire up new routes |
| `pyproject.toml` | Modified | Add pytest-asyncio config |

## Next Phase Readiness

This plan establishes the authentication foundation required for:
- **01-03**: Tenant isolation middleware (needs auth to identify workspace)
- **Phase 2+**: All protected endpoints (need auth dependency)

## Verification Status

- [x] Key generation produces cryptographically secure keys
- [x] Only key hashes stored in database (verified in code review)
- [x] Timing-safe comparison using hmac.compare_digest
- [x] Rotate immediately invalidates old key
- [x] Revoke blocks all subsequent authentication attempts
- [x] 40/40 tests passing
- [x] FastAPI routes import successfully
- [x] Auth dependencies resolve correctly
