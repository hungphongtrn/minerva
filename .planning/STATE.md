# STATE

## Project Reference

- **Project:** Picoclaw Multi-Tenant OSS Runtime
- **Core value:** Teams can run Picoclaw safely for many users with strong isolation and predictable behavior, without building orchestration and sandbox infrastructure.
- **Current milestone scope:** v1 OSS self-hosted runtime foundation.
- **Roadmap depth:** standard
- **Current focus:** Phase 2 - Workspace Lifecycle and Agent Pack Portability

## Current Position

- **Phase:** 2 of 5 (Workspace Lifecycle and Agent Pack Portability)
- **Plan status:** Phase 1 complete and verified; Phase 2 not started
- **Execution status:** Phase 1 passed (6/6 must-haves verified)
- **Progress bar:** [███-------] 27%

```mermaid
flowchart LR
  S1[01-01: Foundation ✓] --> S2[01-02: Auth Endpoints ✓]
  S2 --> S3[01-03: Tenant Isolation ✓]
  S3 --> S4[01-04: Guest + Policy ✓]
  S4 --> S5[01-05: Acceptance Tests ✓]
  S5 --> S6[Verification: Gaps Found ⚠]
  S6 --> S7[01-06: RLS Context ✓]
  S7 --> S8[01-08: Gap 3 Closure ✓]
  S8 --> S9[01-07: Role Resolution ✓]
  S9 --> S10[Verification: Passed ✓]
  S10 --> S11[01-09: Member Mutation Fix ✓]
  S11 --> S12[Phase 2: Agent Packs ◆]
```

## Performance Metrics

- **v1 requirements total:** 36
- **Requirements mapped to phases:** 36
- **Coverage ratio:** 100%
- **Completed phases:** 1/5
- **Completed plans:** 9/15
- **Completed requirements:** 8/36
- **Phase 1 verification score:** 6/6 must-haves verified (all gaps closed via 01-09)
- **Blocking requirements:** None

## Accumulated Context

### Decisions

| ID | Date | Plan | Decision | Rationale |
|----|------|------|----------|-----------|
| ORIG-001 | 2026-02-23 | ROADMAP | Phase structure derived from v1 requirement clusters and dependency order | Natural grouping of related features |
| ORIG-002 | 2026-02-23 | ROADMAP | User-centric tenancy is preserved as a first-class invariant | Core product value |
| ORIG-003 | 2026-02-23 | ROADMAP | Checkpoint durability and immutable audit history are core runtime behavior | Compliance and observability requirements |
| ORIG-004 | 2026-02-23 | ROADMAP | Agent workflow invariant: `define templates -> create agent pack -> infrastructure handles scale` | Simplified UX |
| ORIG-005 | 2026-02-23 | ROADMAP | Agent pack portability is first-class in v1 | Run anywhere philosophy |
| ORIG-006 | 2026-02-23 | ROADMAP | Guest-mode requests use random ephemeral identities and skip persistence | Privacy and simplicity |
| D-01-01-001 | 2026-02-23 | 01-01 | Use lazy initialization for SQLAlchemy engine and session factory | Allow Alembic import without database connection |
| D-01-01-002 | 2026-02-23 | 01-01 | Use UUID primary keys for all identity tables | Distributed system compatibility and security |
| D-01-01-003 | 2026-02-23 | 01-01 | Apply both ENABLE and FORCE ROW Level Security on tenant tables | Ensure consistent tenant isolation, prevent owner bypass |
| D-01-01-004 | 2026-02-23 | 01-01 | Create placeholder RLS policies with 'true' condition in initial migration | Framework in place, policies refined in later phases |
| D-01-02-001 | 2026-02-23 | 01-02 | Use secrets.token_urlsafe for cryptographically secure key generation | Python's secrets module provides highest quality randomness |
| D-01-02-002 | 2026-02-23 | 01-02 | Use SHA-256 hashing with hmac.compare_digest for timing-safe validation | Prevents timing attacks by ensuring constant-time comparison |
| D-01-02-003 | 2026-02-23 | 01-02 | Store only key hashes in database, never plaintext keys | Security best practice - prevents key extraction if DB compromised |
| D-01-02-004 | 2026-02-23 | 01-02 | Support both X-Api-Key header and Authorization: Bearer token formats | Flexibility for different client implementations and API conventions |
| D-01-02-005 | 2026-02-23 | 01-02 | Key rotation preserves key ID but changes material | Allows tracking key lineage while ensuring security |
| D-01-02-006 | 2026-02-23 | 01-02 | Key revocation sets is_active=False rather than deleting records | Preserves audit trail and allows recovery if needed |
| D-01-04-001 | 2026-02-23 | 01-04 | Use cryptographically strong random IDs for guest principals using secrets.token_urlsafe | Consistent with API key generation approach |
| D-01-04-002 | 2026-02-23 | 01-04 | Guest principals are dataclasses with frozen=True for immutability and safety | Prevents accidental mutation of identity |
| D-01-04-003 | 2026-02-23 | 01-04 | Runtime policy engine implements pure functions with default-deny semantics | Clear, testable, secure policy logic |
| D-01-04-004 | 2026-02-23 | 01-04 | Enforcer methods raise PolicyViolationError instead of returning bool for fail-fast behavior | Prevents bypass bugs, explicit error handling |
| D-01-04-005 | 2026-02-23 | 01-04 | Wildcard subdomain matching (e.g., *.example.com) supported in egress policy | Flexible egress control without enumerating all subdomains |
| D-01-04-006 | 2026-02-23 | 01-04 | Guest persistence guard uses PermissionError with descriptive message for clarity | Clear error messages for API consumers |
| D-01-05-001 | 2026-02-23 | 01-05 | Use file-based SQLite for integration tests to share database state between test fixtures and test client | Required for proper HTTP integration testing |
| D-01-05-002 | 2026-02-23 | 01-05 | Acceptance tests map 1:1 to roadmap success criteria for traceability | Ensures every requirement is provably observable |
| D-01-05-003 | 2026-02-23 | 01-05 | Security regression tests use defensive patterns that pass even if underlying behavior changes | Documents expected security behavior without brittle assertions |
| D-01-05-004 | 2026-02-23 | 01-05 | Expected failures documented for SQLite/PostgreSQL RLS compatibility differences | Clear documentation of test environment limitations |
| D-01-06-001 | 2026-02-23 | 01-06 | Use SELECT set_config(..., true) for transaction-local RLS context | Transaction-local settings auto-clear; no manual cleanup needed |
| D-01-06-002 | 2026-02-23 | 01-06 | Skip RLS context for non-PostgreSQL dialects | SQLite tests run without SQL syntax errors |
| D-01-06-003 | 2026-02-23 | 01-06 | Cast UUIDs to text for current_setting() comparison | PostgreSQL current_setting() returns text; avoids type mismatches |
| D-01-06-004 | 2026-02-23 | 01-06 | Use COALESCE with empty string for unset context | Safe handling fails closed (no match) when context unset |
| D-01-08-001 | 2026-02-23 | 01-08 | Thread runtime intents through explicit fields (requested_egress_urls, requested_tools) with fallback extraction from input | Allows both explicit policy intent declaration and backward-compatible input-based inference |
| D-01-08-002 | 2026-02-23 | 01-08 | Policy violation errors include action, resource, and reason in structured format | Makes denials diagnosable and testable while maintaining security |
| D-01-08-003 | 2026-02-23 | 01-08 | HTTP 403 responses include parseable JSON detail with error, status, action, resource, and reason fields | API consumers can programmatically handle different denial types |
| D-01-08-004 | 2026-02-23 | 01-08 | Service-level tests verify real enforcement with actual RuntimeEnforcer, not mocks | Prevents bypass via mocking and ensures default-deny semantics are enforced |
| D-01-07-001 | 2026-02-23 | 01-07 | Workspace fixtures automatically create owner membership records | Ensures all tests have consistent authorization context without requiring every test to explicitly request membership fixtures |
| D-01-07-002 | 2026-02-23 | 01-07 | Migration backfills existing API keys by binding to workspace owner | Maintains backward compatibility while enabling new membership-backed authorization |
| D-01-07-003 | 2026-02-23 | 01-07 | Return structured 403 responses with descriptive error details when no membership is found | Clear error messages help API consumers understand authorization failures |
| D-01-09-001 | 2026-02-23 | 01-09 | Remove all mutation permissions (CREATE/UPDATE/DELETE) from MEMBER role on WORKSPACE_RESOURCE | AUTH-05 requires deterministic, observable role divergence; member permissions violated this requirement |
| D-01-09-002 | 2026-02-23 | 01-09 | Add both positive and negative assertions in tests | Ensures tests fail if permissions are accidentally reintroduced or if owner/admin permissions regress |
| D-01-09-003 | 2026-02-23 | 01-09 | Include explicit UAT scenario test in integration suite | Directly covers the reported issue: "Member POST /workspaces/{workspace_id}/resources returned 201; expected 403" |

### TODOs

- [x] Create executable plan for Phase 1.
- [x] Execute Plan 01-01: Bootstrap identity foundation
- [x] Execute Plan 01-02: Authentication endpoints
- [x] Execute Plan 01-03: Tenant isolation middleware
- [x] Execute Plan 01-04: Guest identity and runtime policy
- [x] Execute Plan 01-05: Phase 1 acceptance and security regression tests
- [x] Plan and execute gap-closure work for verifier findings (01-06, 01-07, 01-08 complete)
- [x] Execute Plan 01-07: Membership-backed role resolution
- [x] Re-run Phase 1 verification to achieve `passed` status
- [x] Execute Plan 01-09: Close member workspace resource mutation gap
- [ ] Begin Phase 2: Workspace Lifecycle and Agent Pack Portability

### Blockers

- None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Create a docker compose to spin up Postgres quickly. | 2026-02-23 | fb4c481 | [001-create-a-docker-compose-to-spin-up-postg](./quick/001-create-a-docker-compose-to-spin-up-postg/) |

## Session Continuity

- **Last completed artifact:** `01-identity-and-policy-baseline-VERIFICATION.md` (status: `passed`)
- **Last activity:** 2026-02-23 - Re-verified Phase 1 after 01-09 gap closure (6/6 must-haves)
- **Traceability source of truth:** `.planning/REQUIREMENTS.md` section `Traceability`
- **Next command:** `/gsd-discuss-phase 2`
- **Recovery note:** If context is lost, resume from `.planning/phases/01-identity-and-policy-baseline/01-identity-and-policy-baseline-VERIFICATION.md`
- **Last session:** 2026-02-23 - Phase 1 verified passed after gap closure via 01-06/01-07/01-08/01-09
- **Commits:** fc2e9bb, b4debf9, 7658dc9, 3c933ea (01-06); 7676310, 412f4a4, 0911f43, f6ccf9a (01-08); c4637e1, b8b63a8, 051bcc0, 931f2da (01-07); d66f658, 3daffed (01-09)

---
*Initialized: 2026-02-23*
*Updated: 2026-02-23 (Phase 1 re-verified passed after 01-09 gap closure)*
