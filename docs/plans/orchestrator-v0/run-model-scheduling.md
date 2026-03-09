# Run Model + Scheduling Implementation Plan

## 1. Problem Statement and Goal

### Problem
Minerva needs a robust run orchestration layer to manage agent execution lifecycles. Currently, there is no defined model for:
- Tracking run state transitions across the execution pipeline
- Ensuring serial execution per user (preventing concurrent runs that could corrupt shared workspace state)
- Providing reliable cancellation and timeout mechanisms

### Goal
Implement the foundational run model and scheduling infrastructure that:
- Defines clear run states: `queued` → `leased` → `running` → `completed`/`failed`/`cancelled`
- Enforces per-user serialization via a queue/lease mechanism (one active run per `user_id`)
- Supports cancellation and timeouts with proper `AbortSignal` propagation through the entire execution stack
- Integrates with the pi-agent-core event stream and SSE output

### Success Criteria
- [ ] Run state machine is implemented and persisted
- [ ] Queue/lease mechanism prevents concurrent runs for same user
- [ ] Cancellation propagates from API through to Daytona sandbox
- [ ] Timeouts are enforced at orchestrator level
- [ ] All state transitions are observable via events

---

## 2. File-Level Changes

### 2.1 New Files

| File | Purpose | Description |
|------|---------|-------------|
| `src/orchestrator/types.ts` | Domain types | RunState enum, Run interface, RunMetadata, Lease types |
| `src/orchestrator/models.ts` | State machine | Run state definitions and transition logic |
| `src/orchestrator/queue.ts` | Queue service | Per-user run queue with FIFO ordering |
| `src/orchestrator/lease.ts` | Lease service | Distributed lease management for run acquisition |
| `src/orchestrator/run-manager.ts` | Run lifecycle | High-level run creation, state management, completion |
| `src/orchestrator/scheduler.ts` | Scheduler | Orchestrates queue consumption and lease acquisition |
| `src/orchestrator/cancellation.ts` | Cancellation | AbortController management and signal propagation |
| `src/orchestrator/timeout.ts` | Timeouts | Run timeout enforcement and cleanup |
| `src/orchestrator/errors.ts` | Error types | Run-specific error classes (RunTimeoutError, RunCancelledError) |
| `src/api/routes/runs.ts` | API routes | HTTP endpoints for run lifecycle (create, status, cancel) |
| `src/api/sse/run-stream.ts` | SSE streaming | Run event streaming with proper backpressure |

### 2.2 Modified Files

| File | Changes |
|------|---------|
| `src/orchestrator/index.ts` | Export new run management modules |
| `src/orchestrator/worker.ts` | Integrate AbortSignal into agent loop execution |
| `src/config/index.ts` | Add run queue and timeout configuration |
| `src/providers/db/schema.ts` | Add runs table schema with state, lease, and metadata fields |

---

## 3. Key Interfaces and Types

### 3.1 Run State Model

```typescript
// src/orchestrator/types.ts

export enum RunState {
  QUEUED = 'queued',           // Waiting in queue
  LEASED = 'leased',           // Acquired lease, preparing sandbox
  RUNNING = 'running',         // Agent loop active
  COMPLETED = 'completed',     // Finished successfully
  FAILED = 'failed',           // Error during execution
  CANCELLED = 'cancelled',     // User or system cancellation
  TIMED_OUT = 'timed_out',     // Exceeded max duration
}

export interface Run {
  id: string;                   // ULID run identifier
  userId: string;               // Owner
  state: RunState;
  
  // Queue/Lease metadata
  queuePosition?: number;       // Position in FIFO queue (null when active)
  leaseToken?: string;          // Unique lease token (ULID)
  leaseExpiresAt?: Date;        // Lease TTL for crash recovery
  
  // Timing
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  timeoutAt?: Date;             // Scheduled timeout
  
  // Configuration
  maxDurationMs: number;        // Hard timeout limit
  
  // Context
  agentPackId: string;
  prompt: string;
  
  // Results
  error?: string;
  finalMessages?: AgentMessage[];
}

export interface RunMetadata {
  runId: string;
  state: RunState;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  queuePosition?: number;
}
```

### 3.2 Lease Interface

```typescript
// src/orchestrator/lease.ts

export interface Lease {
  runId: string;
  token: string;
  acquiredAt: Date;
  expiresAt: Date;
}

export interface LeaseManager {
  acquire(userId: string, runId: string, ttlMs: number): Promise<Lease | null>;
  release(leaseToken: string): Promise<void>;
  extend(leaseToken: string, additionalMs: number): Promise<void>;
  isActive(userId: string): Promise<boolean>;
  getActiveRun(userId: string): Promise<string | null>;
}
```

### 3.3 Queue Interface

```typescript
// src/orchestrator/queue.ts

export interface RunQueue {
  enqueue(runId: string, userId: string): Promise<number>;  // Returns position
  dequeue(userId: string): Promise<string | null>;          // Returns next runId
  peek(userId: string): Promise<string | null>;             // View without removing
  remove(runId: string): Promise<boolean>;
  getPosition(runId: string): Promise<number | null>;
  getLength(userId: string): Promise<number>;
}
```

### 3.4 Cancellation Context

```typescript
// src/orchestrator/cancellation.ts

export interface CancellationContext {
  runId: string;
  controller: AbortController;
  signal: AbortSignal;
  isCancelled: boolean;
  cancel(reason?: string): void;
}

export interface CancellationRegistry {
  create(runId: string): CancellationContext;
  get(runId: string): CancellationContext | undefined;
  remove(runId: string): void;
  cancel(runId: string, reason?: string): boolean;
  cancelAll(reason?: string): void;
}
```

### 3.5 State Transitions

Valid transitions (enforced in `src/orchestrator/models.ts`):

```
QUEUED → LEASED → RUNNING → COMPLETED
                      ↓
                   FAILED
                      ↓
                   CANCELLED
                      ↓
                   TIMED_OUT

QUEUED → CANCELLED (if user cancels while queued)
LEASED → CANCELLED (if user cancels during setup)
RUNNING → CANCELLED (if user cancels during execution)
RUNNING → TIMED_OUT (if maxDuration exceeded)
```

---

## 4. Test Strategy

### 4.1 Unit Tests

| Module | Test Coverage | Test File |
|--------|--------------|-----------|
| State machine | All valid/invalid transitions | `src/orchestrator/models.test.ts` |
| Queue | FIFO ordering, removal, position tracking | `src/orchestrator/queue.test.ts` |
| Lease | Acquisition, release, extension, TTL | `src/orchestrator/lease.test.ts` |
| Cancellation | Signal propagation, registry cleanup | `src/orchestrator/cancellation.test.ts` |
| Timeout | Scheduling, enforcement, cleanup | `src/orchestrator/timeout.test.ts` |

**Test Commands:**
```bash
# Run all orchestrator tests
npm test -- src/orchestrator/

# Run with coverage
npm test -- --coverage src/orchestrator/

# Watch mode for development
npm test -- --watch src/orchestrator/
```

### 4.2 Integration Tests

| Scenario | Test File | Description |
|----------|-----------|-------------|
| End-to-end run lifecycle | `tests/integration/run-lifecycle.test.ts` | Create → Queue → Lease → Run → Complete |
| Per-user serialization | `tests/integration/concurrency.test.ts` | Multiple runs for same user are serialized |
| Cancellation flow | `tests/integration/cancellation.test.ts` | Cancel at each state, verify signal propagation |
| Timeout enforcement | `tests/integration/timeout.test.ts` | Long-running run is terminated |
| Crash recovery | `tests/integration/recovery.test.ts` | Lease expires, run is marked failed |

**Integration Test Commands:**
```bash
# Run integration tests (requires test DB)
npm run test:integration -- tests/integration/run-lifecycle.test.ts

# Run with testcontainers for isolation
npm run test:integration:container
```

### 4.3 Test Utilities

Create `src/test-utils/run-factory.ts` for test data generation:
- `createRun(overrides?: Partial<Run>): Run`
- `createQueuedRun(userId: string): Run`
- `createRunningRun(userId: string): Run`

---

## 5. Implementation Phases

### Phase 1: Core Types and State Machine (2.1)
- [ ] Define RunState enum and Run interface
- [ ] Implement state transition validation
- [ ] Add database migration for runs table

### Phase 2: Queue and Lease (2.2)
- [ ] Implement in-memory queue (v0, can be swapped for Redis later)
- [ ] Implement lease manager with TTL
- [ ] Add scheduler to consume queue and acquire leases

### Phase 3: Run Manager (2.1 + 2.2 integration)
- [ ] Implement RunManager for CRUD and lifecycle
- [ ] Wire queue → lease → run execution
- [ ] Add state persistence

### Phase 4: Cancellation and Timeouts (2.3)
- [ ] Implement CancellationRegistry
- [ ] Add AbortSignal propagation through agent loop
- [ ] Implement timeout scheduler
- [ ] Wire cancellation into API routes

### Phase 5: API and SSE (integration)
- [ ] Add HTTP endpoints for run management
- [ ] Implement SSE stream with run events
- [ ] Add integration tests

---

## 6. Dependencies on Other Sections

| Dependency | Section | Impact |
|------------|---------|--------|
| Database schema | 1.x Infrastructure | Requires runs table migration |
| Sandbox adapter | 3.x Sandbox Execution | Run leases sandbox before RUNNING state |
| Agent worker | 4.x Agent Integration | Worker consumes runs and reports state |
| Event streaming | 5.x Event Streaming | Run state changes emit events to SSE |

**Dependency Graph:**
```
Run Model + Scheduling (this section)
    ↓ depends on
Database/Infrastructure
    ↓ used by
Sandbox Adapter ← → Agent Worker
    ↓
Event Streaming
```

---

## 7. Reference Links

### Documentation
- [Proposal](../../openspec/changes/orchestrator-v0/proposal.md) - Change proposal with capabilities overview
- [Design](../../openspec/changes/orchestrator-v0/design.md) - Design decisions and constraints
- [Architecture v0](../../architecture/agent-runtime-v0.md) - Component overview and state machine
- [Coding Standards](../../CODING_STANDARDS.md) - Code quality and dependency rules

### Research
- [pi-agent-core Events](../../research/pi-agent-core/events.md) - Event model for run streaming
- [pi-agent-core API](../../research/pi-agent-core/api-reference.md) - Agent loop integration

### Related Beans
- Parent: `minerva-5rrj` (orchestrator-v0 overall)
- Siblings:
  - Tool Execution (Section 3.x)
  - Event Streaming (Section 5.x)

---

## 8. Open Questions / Notes

1. **Persistence strategy**: Start with in-memory queue/lease for v0, migrate to Redis for multi-instance deployments
2. **Lease TTL**: Default 30 seconds for acquisition, extendable during execution
3. **Timeout limits**: Configurable per-run, default 10 minutes, max 1 hour
4. **Queue fairness**: Per-user FIFO; consider priority queue for future versions
5. **Cleanup**: Implement lease expiry job to recover from crashed workers
