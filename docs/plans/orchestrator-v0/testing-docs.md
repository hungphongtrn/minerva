# Implementation Plan: Testing + Documentation

**Bean**: minerva-7euj  
**Scope**: Section 7.x (Testing + Docs)  
**Target**: Comprehensive test coverage and API documentation

---

## 1. Problem Statement and Goal

### Problem
Minerva orchestrator v0 requires comprehensive testing to ensure correctness of critical systems:
- **Queue/Lease behavior**: Single active run per user is a core invariant that must be thoroughly tested
- **SSE event sequencing**: Monotonic sequence numbers and clean termination are essential for reliable UI consumption
- **Sandbox execution**: Integration with Daytona must be validated end-to-end
- **Documentation**: API contracts and event schemas must be documented for consumers

### Goal
Implement a complete testing suite and documentation update that:
- Verifies queue/lease behavior prevents concurrent runs per user
- Validates SSE sequence monotonicity and proper stream termination
- Provides integration testing harness for Daytona sandbox execution
- Documents the implemented API endpoints and event schemas

### Success Criteria
- [ ] Unit tests cover queue/lease single-active-run invariant (100% branch coverage)
- [ ] Unit tests validate SSE `seq` monotonicity and termination at run completion
- [ ] Integration test harness executes bash command in Daytona and streams output
- [ ] API documentation reflects all implemented endpoints and event schemas

---

## 2. File-Level Changes

### 2.1 New Test Files

| File | Purpose | Description |
|------|---------|-------------|
| `tests/unit/orchestrator/queue.test.ts` | Queue tests | FIFO ordering, position tracking, concurrent enqueue |
| `tests/unit/orchestrator/lease.test.ts` | Lease tests | Acquisition, TTL, release, extension |
| `tests/unit/orchestrator/serialization.test.ts` | E2E serialization | Single active run per user invariant |
| `tests/unit/sse/envelope.test.ts` | Envelope tests | Seq generation, timestamp format |
| `tests/unit/sse/sequencer.test.ts` | Sequencer tests | Monotonicity, reset, cleanup |
| `tests/unit/sse/stream.test.ts` | Stream tests | Termination on run completion |
| `tests/integration/daytona-bash.test.ts` | Bash integration | Execute command, stream stdout/stderr |
| `tests/integration/sse-e2e.test.ts` | SSE integration | Full run with event validation |
| `tests/test-utils/factories.ts` | Test factories | Run, event, and workspace fixtures |
| `tests/test-utils/sse-client.ts` | SSE test client | EventSource wrapper for tests |
| `tests/test-utils/daytona-mock.ts` | Daytona mocking | Mock adapter for unit tests |

### 2.2 Modified Files

| File | Changes |
|------|---------|
| `package.json` | Add test scripts, devDependencies (vitest, @vitest/coverage-v8, testcontainers) |
| `vitest.config.ts` | Configure unit and integration test projects |
| `tests/setup.ts` | Global test setup, mocks, environment config |
| `tests/tsconfig.json` | TypeScript config for test files |

### 2.3 New Documentation Files

| File | Purpose | Description |
|------|---------|-------------|
| `docs/api/INDEX.md` | API overview | Entry point for API documentation |
| `docs/api/endpoints.md` | Endpoint reference | HTTP endpoints with request/response schemas |
| `docs/api/sse-schema.md` | SSE schema | Event types, payloads, sequencing |
| `docs/api/authentication.md` | Auth guide | Authentication and authorization |
| `docs/testing/INDEX.md` | Testing guide | How to run tests, write new tests |
| `docs/testing/strategy.md` | Test strategy | Unit vs integration, mocking approach |

---

## 3. Key Interfaces and Types to Define

### 3.1 Test Utilities

```typescript
// tests/test-utils/factories.ts

export interface RunFactoryOptions {
  userId?: string;
  state?: RunState;
  queuePosition?: number;
  leaseToken?: string;
}

export function createRun(overrides?: Partial<Run>): Run;
export function createQueuedRun(userId: string): Run;
export function createRunningRun(userId: string): Run;
export function createCompletedRun(userId: string): Run;
```

```typescript
// tests/test-utils/sse-client.ts

export interface SSETestClient {
  connect(url: string): Promise<void>;
  disconnect(): void;
  getEvents(): SSEEventEnvelope[];
  waitForEvent(type: SSEEventType, timeoutMs?: number): Promise<SSEEventEnvelope>;
  waitForTerminal(timeoutMs?: number): Promise<void>;
  assertMonotonicSeq(): void;
}

export function createSSEClient(): SSETestClient;
```

```typescript
// tests/test-utils/daytona-mock.ts

export interface MockSandboxAdapter extends ISandboxAdapter {
  setExecutionResult(command: string, result: ExecutionResult): void;
  setFileContent(path: string, content: string): void;
  getWrittenFiles(): Map<string, string>;
  getExecutedCommands(): string[];
}

export function createMockAdapter(): MockSandboxAdapter;
```

### 3.2 Test Assertions

```typescript
// tests/test-utils/assertions.ts

export function assertSingleActiveRunPerUser(
  runs: Run[], 
  userId: string
): void;

export function assertMonotonicSeq(
  events: SSEEventEnvelope[],
  strict?: boolean
): void;

export function assertStreamTerminated(
  events: SSEEventEnvelope[],
  expectedState: RunState
): void;
```

---

## 4. Test Strategy

### 4.1 Unit Tests: Queue/Lease Behavior (7.1)

**Test File**: `tests/unit/orchestrator/queue.test.ts`

| Test Case | Description |
|-----------|-------------|
| `enqueue adds run to user queue` | Single run enqueued, position 1 |
| `enqueue maintains FIFO order` | Multiple runs, positions increment |
| `dequeue returns first run` | FIFO behavior verified |
| `dequeue returns null for empty queue` | Empty queue handling |
| `remove deletes specific run` | Run removal by ID |
| `getPosition returns correct position` | Position tracking accuracy |

**Test File**: `tests/unit/orchestrator/lease.test.ts`

| Test Case | Description |
|-----------|-------------|
| `acquire grants lease when no active run` | Lease granted for user |
| `acquire returns null when lease held` | Single lease per user enforced |
| `acquire respects TTL` | Lease expires after TTL |
| `release frees lease` | Lease can be released |
| `extend prolongs lease` | Lease TTL can be extended |
| `isActive returns correct state` | Lease state query |

**Test File**: `tests/unit/orchestrator/serialization.test.ts`

| Test Case | Description |
|-----------|-------------|
| `concurrent runs for different users allowed` | Multi-user parallelism |
| `second run for same user is queued` | Serialization enforced |
| `active run blocks new runs` | Run state prevents new lease |
| `completed run allows new lease` | Cleanup enables new runs |
| `cancelled run releases lease` | Cancellation enables new runs |

**Test Commands**:
```bash
# Run queue/lease unit tests
npm test -- tests/unit/orchestrator/queue.test.ts
npm test -- tests/unit/orchestrator/lease.test.ts
npm test -- tests/unit/orchestrator/serialization.test.ts

# Run with coverage
npm test -- --coverage tests/unit/orchestrator/

# Watch mode
npm test -- --watch tests/unit/orchestrator/
```

### 4.2 Unit Tests: SSE Sequencing (7.2)

**Test File**: `tests/unit/sse/envelope.test.ts`

| Test Case | Description |
|-----------|-------------|
| `envelope has required fields` | type, run_id, ts, seq, payload |
| `timestamp is ISO 8601 format` | Timestamp format validation |
| `payload is type-safe` | Generic payload typing |

**Test File**: `tests/unit/sse/sequencer.test.ts`

| Test Case | Description |
|-----------|-------------|
| `seq starts at 1` | Initial sequence number |
| `seq increments monotonically` | Each event increments by 1 |
| `seq is isolated per run` | Separate counters per run_id |
| `reset sets seq to specified value` | Reset functionality |
| `cleanup removes counter` | Memory cleanup on run end |
| `concurrent events get unique seq` | Race condition safety |

**Test File**: `tests/unit/sse/stream.test.ts`

| Test Case | Description |
|-----------|-------------|
| `stream closes on run completed` | Terminal state triggers close |
| `stream closes on run failed` | Failed state triggers close |
| `stream closes on run cancelled` | Cancelled state triggers close |
| `stream closes on run timed_out` | Timeout triggers close |
| `stream stays open for non-terminal states` | Active runs continue |
| `close is idempotent` | Multiple closes safe |

**Test Commands**:
```bash
# Run SSE unit tests
npm test -- tests/unit/sse/

# Run with coverage
npm test -- --coverage tests/unit/sse/
```

### 4.3 Integration Test: Daytona Bash (7.3)

**Test File**: `tests/integration/daytona-bash.test.ts`

**Prerequisites**:
- Daytona server running (local or remote)
- Valid Daytona API credentials in environment
- Test workspace can be created/destroyed

| Test Case | Description |
|-----------|-------------|
| `execute echo command` | Basic command execution |
| `stream stdout chunks` | Real-time stdout streaming |
| `stream stderr chunks` | Real-time stderr streaming |
| `capture exit code` | Exit status returned |
| `respect timeout` | Long command times out |
| `cancel via AbortSignal` | Signal cancellation works |
| `handle large output` | Large stdout handled |
| `handle command failure` | Non-zero exit handled |

**Test Harness**:
```typescript
// tests/integration/daytona-bash.test.ts

describe('Daytona Bash Integration', () => {
  let adapter: ISandboxAdapter;
  let workspace: Workspace;

  beforeAll(async () => {
    adapter = createDaytonaAdapter();
    workspace = await adapter.getOrCreateWorkspace('test-user', WorkspaceStrategy.PER_RUN);
  });

  afterAll(async () => {
    await adapter.destroyWorkspace(workspace.id);
  });

  it('should execute echo and stream output', async () => {
    const chunks: ExecutionChunk[] = [];
    
    for await (const chunk of adapter.execute(workspace.id, 'echo "Hello, World!"')) {
      chunks.push(chunk);
    }

    const stdout = chunks
      .filter(c => c.type === 'stdout')
      .map(c => c.data)
      .join('');
    
    const exitCode = chunks.find(c => c.type === 'exit')?.data;
    
    expect(stdout.trim()).toBe('Hello, World!');
    expect(exitCode).toBe(0);
  });
});
```

**Test Commands**:
```bash
# Run Daytona integration tests (requires Daytona server)
npm run test:integration -- tests/integration/daytona-bash.test.ts

# Run with testcontainers (if supported)
npm run test:integration:container

# Run all integration tests
npm run test:integration
```

**Environment Setup**:
```bash
# .env.test
DAYTONA_SERVER_URL=http://localhost:3000
DAYTONA_API_KEY=test-api-key
DAYTONA_TARGET=local
```

### 4.4 Integration Test: SSE E2E (7.3 extended)

**Test File**: `tests/integration/sse-e2e.test.ts`

| Test Case | Description |
|-----------|-------------|
| `full run emits all lifecycle events` | queued → started → completed |
| `seq numbers are monotonic` | Strict ordering verified |
| `stream terminates after completion` | Clean termination |
| `tool execution events are emitted` | bash tool events streamed |
| `multiple clients receive same events` | Broadcast verified |
| `reconnect with Last-Event-ID replays` | Replay buffer works |

### 4.5 Documentation Update (7.4)

**Updated Files**:

1. **docs/api/endpoints.md**
   - `POST /api/v0/runs` - Create run
   - `GET /api/v0/runs/:runId` - Get run status
   - `POST /api/v0/runs/:runId/cancel` - Cancel run
   - `GET /api/v0/runs/:runId/stream` - SSE stream

2. **docs/api/sse-schema.md**
   - Event envelope format
   - All event types with payloads
   - Sequence number semantics
   - Connection lifecycle

3. **docs/api/authentication.md**
   - Auth mechanism (TBD based on implementation)
   - API key usage
   - Authorization scopes

4. **docs/testing/INDEX.md**
   - Running tests
   - Test structure
   - Writing new tests
   - Mocking guidelines

---

## 5. Dependencies on Other Sections

| Dependency | Section | Impact |
|------------|---------|--------|
| Queue implementation | 2.x Run Model | Unit tests depend on queue interface |
| Lease implementation | 2.x Run Model | Unit tests depend on lease interface |
| SSE envelope | 5.x SSE API | Unit tests depend on envelope types |
| Daytona adapter | 3.x Sandbox | Integration tests need adapter |
| API routes | 1.x Project | Integration tests need HTTP server |
| Run states | 2.x Run Model | Tests need state machine |

**Dependency Graph**:
```
Testing + Docs (this section - 7.x)
    ↓ depends on
Run Model + Scheduling (2.x) - queue, lease, states
    ↓
SSE API (5.x) - envelope, sequencer
    ↓
Daytona Sandbox (3.x) - adapter, execution
    ↓
Project Setup (1.x) - HTTP server, config
```

**Note**: This bean is blocked by completion of core implementation beans. Tests should be written against implemented interfaces, not ahead of implementation.

---

## 6. Implementation Phases

### Phase 1: Test Infrastructure (7.0)
- [ ] Set up vitest configuration
- [ ] Create test directory structure
- [ ] Implement test factories and utilities
- [ ] Add test scripts to package.json

### Phase 2: Unit Tests - Queue/Lease (7.1)
- [ ] Write queue unit tests
- [ ] Write lease unit tests
- [ ] Write serialization integration tests
- [ ] Achieve 100% branch coverage on queue/lease

### Phase 3: Unit Tests - SSE (7.2)
- [ ] Write envelope unit tests
- [ ] Write sequencer unit tests
- [ ] Write stream termination tests
- [ ] Verify monotonic seq invariant

### Phase 4: Integration Tests (7.3)
- [ ] Set up Daytona test environment
- [ ] Write bash execution integration test
- [ ] Write SSE end-to-end test
- [ ] Document test environment setup

### Phase 5: Documentation (7.4)
- [ ] Document API endpoints
- [ ] Document SSE event schema
- [ ] Document authentication
- [ ] Create testing guide

---

## 7. Configuration

### vitest.config.ts

```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    projects: [
      {
        name: 'unit',
        root: './tests/unit',
        testMatch: ['**/*.test.ts'],
        environment: 'node',
        coverage: {
          provider: 'v8',
          reporter: ['text', 'json', 'html'],
          include: ['src/**/*.ts'],
          exclude: ['src/**/*.d.ts', 'src/**/*.test.ts'],
        },
      },
      {
        name: 'integration',
        root: './tests/integration',
        testMatch: ['**/*.test.ts'],
        environment: 'node',
        setupFiles: ['./setup-integration.ts'],
        testTimeout: 60000, // Longer timeout for integration tests
      },
    ],
  },
});
```

### package.json scripts

```json
{
  "scripts": {
    "test": "vitest run",
    "test:unit": "vitest run --project=unit",
    "test:integration": "vitest run --project=integration",
    "test:watch": "vitest --watch",
    "test:coverage": "vitest run --coverage",
    "test:orchestrator": "vitest run tests/unit/orchestrator/",
    "test:sse": "vitest run tests/unit/sse/"
  }
}
```

---

## 8. Reference Links

### Documentation
- [Project Scope](../../PROJECT.md) - Product boundaries for the orchestrator MVP
- [Process Workflow](../../process/markdown-beans-workflow.md) - Markdown-first planning and bean tracking expectations
- [Architecture v0](../../architecture/agent-runtime-v0.md) - Component overview
- [Coding Standards](../../CODING_STANDARDS.md) - Test quality standards
- [Run Orchestration Reference](../../specs/run-orchestration.md) - Execution states and lifecycle constraints

### Related Plans
- [Run Model + Scheduling](./run-model-scheduling.md) - Queue/lease implementation details
- [SSE API](./sse-api.md) - SSE implementation and event schema
- [Daytona Sandbox Adapter](./daytona-sandbox-adapter.md) - Sandbox execution details
- [Project Setup](./project-setup.md) - TypeScript project structure

### Research
- [pi-agent-core Events](../../research/pi-agent-core/events.md) - Event model for SSE testing
- [pi-agent-core Tools](../../research/pi-agent-core/tools.md) - Tool patterns for bash testing

### External References
- [Vitest Documentation](https://vitest.dev/) - Test framework
- [@daytonaio/sdk](https://www.npmjs.com/package/@daytonaio/sdk) - Daytona SDK for integration tests

### Related Beans
- Parent: `minerva-5rrj` (orchestrator-v0 overall)
- Blocked by:
  - `minerva-goow` - Implementation bean (must complete before testing)
  - `minerva-eegh` - Project setup (test infrastructure)
  - `minerva-g1y9` - Run model (queue/lease implementation)
  - `minerva-ha33` - SSE API (event sequencing)
  - `minerva-derz` - Daytona adapter (bash execution)

---

## 9. Testing Checklist

### Unit Tests
- [ ] Queue: FIFO ordering, position tracking, removal
- [ ] Lease: acquisition, TTL, release, extension
- [ ] Serialization: single active run per user
- [ ] Envelope: required fields, format
- [ ] Sequencer: monotonic seq, per-run isolation
- [ ] Stream: termination on terminal states

### Integration Tests
- [ ] Daytona connection
- [ ] Bash command execution
- [ ] Stdout/stderr streaming
- [ ] Exit code capture
- [ ] Timeout handling
- [ ] Cancellation via signal

### Documentation
- [ ] API endpoints documented
- [ ] SSE schema documented
- [ ] Authentication documented
- [ ] Testing guide created

### Coverage Targets
- [ ] Queue/lease: 100% branch coverage
- [ ] SSE core: 100% branch coverage
- [ ] Overall: >80% coverage

---

*Plan created: 2026-03-09*  
*Status: Draft - awaiting implementation completion*
