---
# minerva-g1y9
title: Run Model + Scheduling
status: completed
type: task
priority: high
tags:
    - harvest
    - orchestrator-v0
created_at: 2026-03-09T08:10:21Z
updated_at: 2026-03-09T09:04:21Z
parent: minerva-5rrj
---

## Plan

📄 **Implementation Plan**: [docs/plans/orchestrator-v0/run-model-scheduling.md](../../docs/plans/orchestrator-v0/run-model-scheduling.md)

## Requirements

- [x] 2.1 Define run IDs, run states (queued/running/completed/failed/cancelled), and minimal run metadata model, run states (queued/running/completed/failed/cancelled), and minimal run metadata model
- [x] 2.2 Implement per-user queue/lease to ensure one active run per user_id to ensure one active run per user_id
- [x] 2.3 Implement cancellation and timeouts at the orchestrator level (AbortSignal propagation) at the orchestrator level (AbortSignal propagation)

## References

- **Proposal**: openspec/changes/orchestrator-v0/proposal.md
- **Design**: openspec/changes/orchestrator-v0/design.md
- **Tasks**: openspec/changes/orchestrator-v0/tasks.md

## Summary of Changes

Implemented the foundational run model and scheduling infrastructure:

### 2.1 Run Model & State Machine
- **src/types/run.ts**: Defined RunState enum (queued, leased, running, completed, failed, cancelled, timed_out), Run interface, RunMetadata, and state transition validation functions
- **src/types/errors.ts**: Created run-specific error classes (RunTimeoutError, RunCancelledError, InvalidStateTransitionError, etc.)

### 2.2 Queue & Lease System
- **src/services/queue.ts**: Implemented InMemoryRunQueue with per-user FIFO ordering
- **src/services/lease.ts**: Implemented InMemoryLeaseManager with TTL-based leases to enforce one active run per user
- **src/services/run-manager.ts**: Orchestrates queue, lease, and state management

### 2.3 Cancellation & Timeouts
- **src/services/cancellation.ts**: Implemented InMemoryCancellationRegistry with AbortController/AbortSignal for cancellation propagation
- **src/services/timeout.ts**: Implemented InMemoryTimeoutManager for scheduling and enforcing run timeouts
- Integrated timeout enforcement into RunManager with automatic state transition to TIMED_OUT

### Testing
- **tests/unit/run-types.test.ts**: 18 tests for state machine validation
- **tests/unit/queue.test.ts**: 16 tests for FIFO queue operations
- **tests/unit/lease.test.ts**: 18 tests for lease acquisition/release/extension
- **tests/unit/cancellation.test.ts**: 18 tests for signal propagation
- **tests/unit/timeout.test.ts**: 14 tests for timeout scheduling
- **tests/unit/run-manager.test.ts**: 34 tests for full lifecycle management

All 120 unit tests pass with 100% coverage of implemented functionality.
