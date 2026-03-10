---
# minerva-7euj
title: Testing + Docs
status: completed
type: task
priority: low
tags:
    - harvest
    - orchestrator-v0
    - verified
created_at: 2026-03-09T08:10:51Z
updated_at: 2026-03-10T04:45:36Z
parent: minerva-5rrj
blocked_by:
    - minerva-goow
---

## Requirements

- [x] 7.1 Add unit tests for queue/lease behavior (single active run per user)
- [x] 7.2 Add unit tests for SSE sequencing (`seq` monotonicity) and termination at run completion
- [x] 7.3 Add integration test (or harness) that runs a simple `bash` command in Daytona and streams output
- [x] 7.4 Update docs to reflect implemented API endpoints and event schema

## References

- **Proposal**: openspec/changes/orchestrator-v0/proposal.md
- **Design**: openspec/changes/orchestrator-v0/design.md
- **Tasks**: openspec/changes/orchestrator-v0/tasks.md



## Plan

See detailed implementation plan: [docs/plans/orchestrator-v0/testing-docs.md](../../../docs/plans/orchestrator-v0/testing-docs.md)

## Summary of Changes

### 7.1 Unit Tests for Queue/Lease Behavior
- Created `tests/unit/orchestrator/serialization.test.ts` with 14 tests
- Tests verify single active run per user invariant
- Covers concurrent runs for different users, serialization for same user, lease blocking, and cleanup on completion/cancellation/failure

### 7.2 Unit Tests for SSE Sequencing
- Created `tests/unit/sse/envelope.test.ts` with 21 tests
- Created `tests/unit/sse/sequencer.test.ts` with 19 tests  
- Created `tests/unit/sse/stream.test.ts` with 20 tests
- Tests verify seq monotonicity (starts at 1, increments by 1, per-run isolation)
- Tests verify stream termination at terminal events (completed, failed, cancelled, timed_out)

### 7.3 Integration Test for Daytona Bash
- Created `tests/integration/daytona-bash.test.ts` with 11 tests
- Tests basic command execution, stdout/stderr streaming, exit codes, timeout handling, working directory, environment variables, and command chaining
- Includes MockSandboxAdapter for testing without real Daytona server
- Can use real Daytona by setting DAYTONA_API_KEY and DAYTONA_SERVER_URL env vars

### 7.4 Documentation Updates
- Created `docs/api/README.md` - API overview and quick start
- Created `docs/api/endpoints.md` - HTTP endpoints with request/response schemas
- Created `docs/api/sse-schema.md` - Event types, payloads, and sequencing
- Created `docs/api/authentication.md` - Authentication methods
- Created `docs/testing/README.md` - Testing guide
- Created `docs/testing/strategy.md` - Test strategy and best practices

### Test Infrastructure
- Updated `vitest.unit.config.ts` with path aliases for cleaner imports
- All new tests passing (60+ new tests total)

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-09

### Results
- All requirements met
- Tests pass
- Code compiles without errors

### Test Summary
**Unit Tests:**
- : 14 tests ✓
- : 21 tests ✓
- : 19 tests ✓
- : 20 tests ✓
- : 16 tests ✓
- : 18 tests ✓
- Total unit tests: 243 passed

**Integration Tests:**
- : 11 tests ✓
- Total integration tests: 23 passed

**Documentation:**
-  ✓
-  ✓
-  ✓
-  ✓
-  ✓
-  ✓

**Infrastructure:**
-  with path aliases ✓
- Code compiles successfully ✓

### Notes
- One unrelated test failure in  (not part of this bean's scope)
- All 60+ new tests for queue/lease, SSE sequencing, and Daytona bash are passing
- Documentation fully reflects implemented API endpoints and event schemas

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-10

### Results
- Verified queue/lease, SSE sequencing, and Daytona bash test coverage is present and passing
- Verified API and testing docs exist under `docs/` and match implemented surfaces
- `npm run test:unit`, `npm run test:integration`, and `npm run typecheck` passed
