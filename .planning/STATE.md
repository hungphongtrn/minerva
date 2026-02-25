# STATE

## Project Reference

- **Project:** Picoclaw Multi-Tenant OSS Runtime
- **Core value:** Teams can run Picoclaw safely for many users with strong isolation and predictable behavior, without building orchestration and sandbox infrastructure.
- **Current milestone scope:** v1 OSS self-hosted runtime foundation.
- **Roadmap depth:** standard
- **Current focus:** Phase 3 - Persistence and Checkpoint Recovery

## Current Position

- **Phase:** 2 of 5 (Workspace Lifecycle and Agent Pack Portability) - COMPLETE
- **Plan status:** Phase 2 COMPLETE (all 12 base plans + all gap closures 02-13 through 02-17)
- **Execution status:** Phase 2 complete with acceptance, security evidence, all UAT gap closures (Tests 4, 7, 9), and Truth 11 profile parity
- **Progress bar:** [██████████] 50%
- **Last completed:** Plan 02-17 (Truth 11 profile parity gap closure)

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
  S11 --> S12[02-01: Schema Foundation ✓]
  S12 --> S13[02-02: Provider Adapters ✓]
  S13 --> S14[02-03: Lifecycle Services ✓]
  S14 --> S15[02-04: Template/Pack Registration ✓]
  S15 --> S16[02-05: API Routes ✓]
  S16 --> S17[02-06: UUID Ownership Fix ✓]
  S17 --> S18[02-07: Scaffold/Portability Gaps ✓]
  S18 --> S19[02-08: Acceptance/Security Green ✓]
  S19 --> S20[02-09: Pack Runtime Wiring ✓]
  S20 --> S21[02-10: Provider Pack Binding ✓]
  S21 --> S22[02-11: Daytona SDK Provider ✓]
  S22 --> S23[02-12: SDK Acceptance/Security ✓]
```

## Performance Metrics

- **v1 requirements total:** 36
- **Requirements mapped to phases:** 36
- **Coverage ratio:** 100%
- **Completed phases:** 2/5
- **Completed plans:** 19/19
- **Completed requirements:** 18/36
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
| D-02-02-001 | 2026-02-24 | 02-02 | Semantic State Contract Over Native Payloads | Services must be provider-agnostic; semantic abstraction ensures consistent routing logic |
| D-02-02-002 | 2026-02-24 | 02-02 | Fail-Closed Behavior for Unknown States | Security and safety - routing to unknown state could cause data leakage or wrong sandbox execution |
| D-02-02-003 | 2026-02-24 | 02-02 | Idempotent Stop Operations | Lease expiration, crash recovery, TTL enforcement may all attempt stop; idempotency prevents error cascades |
| D-02-02-004 | 2026-02-24 | 02-02 | Config-Driven Profile Selection | AGNT-03 requires switching profiles via environment changes, not workflow changes |
| D-02-02-005 | 2026-02-24 | 02-02 | Self-Hosted Daytona First-Class Support | 02-CONTEXT explicitly prioritizes Daytona self-host as a handy option alongside Cloud |
| D-02-01-001 | 2026-02-24 | 02-01 | Partial unique index for active leases | PostgreSQL partial index WHERE released_at IS NULL enforces one active lease per workspace |
| D-02-01-002 | 2026-02-24 | 02-01 | Path-linked pack registration | Store source_path as source of truth with source_digest for stale detection - aligns with Picoclaw filesystem model |
| D-02-01-003 | 2026-02-24 | 02-01 | PostgreSQL native enums for states/status | Better type safety at database level for state/status columns |
| D-02-01-004 | 2026-02-24 | 02-01 | Repository pattern with focused query methods | Each entity has dedicated repository; query logic centralized and testable |
| D-02-04-001 | 2026-02-24 | 02-04 | Idempotent scaffold generation by default | Safe to re-run without corrupting user edits to scaffold files |
| D-02-04-002 | 2026-02-24 | 02-04 | Path traversal protection in scaffold service | Security requirement for filesystem operations - reject paths escaping base directory |
| D-02-04-003 | 2026-02-24 | 02-04 | Deterministic checklist format with machine-readable codes | API consumers can programmatically handle validation results |
| D-02-04-004 | 2026-02-24 | 02-04 | SHA-256 for content digests | Industry standard, stable, widely supported for change detection |
| D-02-04-005 | 2026-02-24 | 02-04 | Repository delegation in pack service | All persistence operations go through AgentPackRepository - consistent with codebase |
| D-02-04-006 | 2026-02-24 | 02-04 | Upsert behavior for pack registration | Natural for path-linked semantics where folder remains source of truth |
| D-02-03-001 | 2026-02-24 | 02-03 | Cross-Database Lease Acquisition | Use explicit locking instead of PostgreSQL-specific syntax for SQLite compatibility |
| D-02-03-002 | 2026-02-24 | 02-03 | Lease TTL Validation Range | 10s-1h for leases, 60s-24h for idle TTL to prevent accidental immediate expiry or indefinite locks |
| D-02-03-003 | 2026-02-24 | 02-03 | LifecycleService as Primary Entrypoint | Routes should not coordinate lease + routing manually; single entrypoint ensures consistent pattern |
| D-02-07-001 | 2026-02-24 | 02-07 | Distinguish explicit vs default base_path in scaffold service | API flows need temp directory support; explicit base needs containment |
| D-02-07-002 | 2026-02-24 | 02-07 | Add workspace parameter to lifecycle service | Prevents wrong workspace selection when user owns multiple workspaces |
| D-02-07-003 | 2026-02-24 | 02-07 | Test client auto-commit on success | Required for multi-request integration tests with shared database |
| D-02-07-004 | 2026-02-24 | 02-07 | Centralize provider exports in __init__.py | Consistent import pattern for acceptance and portability tests |
| D-02-06-001 | 2026-02-24 | 02-06 | Route-local UUID normalization helper | Safer than modifying shared Principal type; focused fix for workspace routes |
| D-02-06-002 | 2026-02-24 | 02-06 | Explicit HTTP errors for identity validation | Clear error messages help API consumers debug authentication issues |
| D-02-06-003 | 2026-02-24 | 02-06 | Clean removal of dead code | Removes ~89 lines of unreachable duplicate logic; reduces drift risk |
| D-02-08-001 | 2026-02-24 | 02-08 | Use hasattr pattern for enum/string compatibility | SQLite returns strings, PostgreSQL returns enums; hasattr provides safe dual-mode handling |
| D-02-08-002 | 2026-02-24 | 02-08 | Return ephemeral routing for guests without workspace | Guest mode must bypass workspace lifecycle entirely |
| D-02-08-003 | 2026-02-24 | 02-08 | Document user-centric model in test docstrings | Clarifies why same-user cross-workspace access succeeds |
| D-02-09-001 | 2026-02-25 | 02-09 | Convert agent_pack_id to UUID at service boundary | Type safety prevents format errors deeper in stack |
| D-02-09-002 | 2026-02-25 | 02-09 | Fail-closed validation before provider provisioning | Security and cost - no orphaned sandboxes on validation failure |
| D-02-09-003 | 2026-02-25 | 02-09 | Handle AgentPackValidationStatus as string constants | SQLite stores as strings, .value attribute caused AttributeError |
| D-02-10-001 | 2026-02-25 | 02-10 | Provider Metadata for Pack Observability | Expose pack binding via provider metadata for provider-agnostic contract |
| D-02-10-002 | 2026-02-25 | 02-10 | Equivalent but Profile-Specific Implementation | Both providers implement same semantic contract with profile-specific internals |
| D-02-11-001 | 2026-02-25 | 02-11 | AsyncDaytona Context Manager Pattern | Use async context manager for proper resource cleanup and SDK best practices |
| D-02-11-002 | 2026-02-25 | 02-11 | Backward-Compatible Constructor | Support both old (api_token) and new (api_key) parameter names for smooth migration |
| D-02-11-003 | 2026-02-25 | 02-11 | Fail-Closed SDK Error Handling | get_active_sandbox returns None on SDK errors to prevent cascading failures |
| D-02-11-004 | 2026-02-25 | 02-11 | Pack Binding Metadata Preservation | Store pack binding info in metadata for routing layer observability |
| D-02-12-001 | 2026-02-25 | 02-12 | SDK Mocking in Integration Tests | Use patch("src.infrastructure.sandbox.providers.daytona.AsyncDaytona") for all Daytona SDK mocking |
| D-02-12-002 | 2026-02-25 | 02-12 | Fix Missing Exception Imports | Auto-fix missing SandboxHealthCheckError and SandboxProviderError imports |
| D-02-13-001 | 2026-02-25 | 02-13 | Request-Scoped Transaction Boundaries | Centralize commit/rollback in get_db() dependency for consistent durability across all mutating routes |
| D-02-13-002 | 2026-02-25 | 02-13 | Production-Equivalent Test Transactions | Integration tests must exercise same commit/rollback lifecycle as production via aligned override_get_db |
| D-02-13-003 | 2026-02-25 | 02-13 | Cross-Request Durability Verification | Durability regressions use separate HTTP requests to force verification of committed (not just flushed) state |
| D-02-14-001 | 2026-02-25 | 02-14 | Fail-Fast Routing Semantics | Non-guest runs return success=False when lifecycle routing fails; prevents execution with null/invalid sandbox |
| D-02-14-002 | 2026-02-25 | 02-14 | Error Type Constants Over String Matching | Use centralized RoutingErrorType class for deterministic error categorization |
| D-02-14-003 | 2026-02-25 | 02-14 | 503 Reserved for Infrastructure Only | HTTP 503 reserved for provider/infrastructure unavailability, not pack validation failures (4xx) |
| D-02-14-004 | 2026-02-25 | 02-14 | Remediation Guidance in Error Responses | All routing errors include 'remediation' field with actionable guidance for self-service debugging |
| D-02-15-001 | 2026-02-25 | 02-15 | Bounded Lease Contention with Exponential Backoff | 10s max wait with exponential backoff (50ms-500ms) prevents indefinite hangs while giving legitimate operations time to complete |
| D-02-15-002 | 2026-02-25 | 02-15 | Explicit FOR UPDATE Row Locking | Pessimistic row locking ensures deterministic serialization without relying on unique constraint races |
| D-02-15-003 | 2026-02-25 | 02-15 | CONFLICT_RETRYABLE with Retry Guidance | Contention timeout returns explicit retry_after_seconds guidance instead of generic errors |
| D-02-16-001 | 2026-02-25 | 02-16 | Provider Singleton Pattern for Integration Tests | Integration tests need shared provider state to properly validate health check behavior |
| D-02-16-002 | 2026-02-25 | 02-16 | TTL Cleanup Enforcement in Routing Path | Request-time TTL cleanup ensures consistent policy enforcement on every routing decision |
| D-02-16-003 | 2026-02-25 | 02-16 | Observable TTL Metadata in API Responses | TTL cleanup status exposed via response fields for user verification and debugging |
| D-02-17-001 | 2026-02-25 | 02-17 | Infrastructure Errors Take Precedence Over Workspace Resolution | Provider failures are infrastructure issues (5xx), must be checked before client errors (4xx) to prevent misclassification |

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
- [x] Execute Plan 02-01: Phase 2 schema foundation for leases, sandboxes, and path-linked agent packs
- [x] Execute Plan 02-02: Provider adapter boundary for local compose and Daytona parity
- [x] Execute Plan 02-03: Workspace lifecycle services
- [x] Execute Plan 02-04: Template scaffold and pack registration
- [x] Execute Plan 02-05: Phase 2 API routes and security tests
- [x] Execute Plan 02-07: Close scaffold/register and profile portability contract gaps
- [x] Execute Plan 02-06: UUID ownership normalization and dead branch removal
- [x] Execute Plan 02-08: Drive acceptance and security suites to green
- [x] Execute Plan 02-09: Close agent pack runtime wiring gap with fail-closed validation
- [x] Execute Plan 02-10: Close UAT Test 4 gap with provider pack binding parity
- [x] Execute Plan 02-11: Replace Daytona simulation with SDK-backed lifecycle
- [x] Execute Plan 02-12: Add acceptance and security evidence for Daytona SDK
- [x] Execute Plan 02-13: Close durability gap with transaction boundaries and regression coverage
- [x] Execute Plan 02-14: Close UAT Test 4 gap with fail-fast routing and pack-specific errors
- [x] Execute Plan 02-16: Close UAT Test 9 with idle TTL enforcement and observability
- [x] Execute Plan 02-14: Close UAT Test 4 gap with fail-fast routing
- [x] Execute Plan 02-15: Close UAT Test 7 gap with bounded lease contention
- [x] Execute Plan 02-17: Close Truth 11 gap with daytona profile parity and CI evidence

### Blockers

- None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Create a docker compose to spin up Postgres quickly. | 2026-02-23 | fb4c481 | [001-create-a-docker-compose-to-spin-up-postg](./quick/001-create-a-docker-compose-to-spin-up-postg/) |

## Session Continuity

- **Last completed artifact:** `02-17-SUMMARY.md` (Truth 11 profile parity gap closure)
- **Last activity:** 2026-02-25 - Completed plan 02-17 (daytona valid-pack routing fix, parity regression tests, CI harness evidence)
- **Traceability source of truth:** `.planning/REQUIREMENTS.md` section `Traceability`
- **Next plans:** Phase 3 - Persistence and Checkpoint Recovery
- **Recovery note:** If context is lost, resume from `.planning/phases/02-workspace-lifecycle-and-agent-pack-portability/02-17-SUMMARY.md`
- **Last session:** 2026-02-25 - Plan 02-17 complete (daytona valid-pack 400→503 fix, 4 new parity tests, CI harness with required dual-profile execution)
- **Commits:** ...; fe6e5bf, ac7593b, dcb9274 (02-16); 59dda9c, 1e96b86, f57dd22 (02-17)

---
*Initialized: 2026-02-23*
*Updated: 2026-02-25 (Plan 02-17 complete - Truth 11 gap closure with daytona profile parity. All Phase 2 truths verified 11/11.)*
