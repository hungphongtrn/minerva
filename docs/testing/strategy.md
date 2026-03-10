# Test Strategy

## Overview

This document outlines the testing strategy for Minerva Orchestrator, covering unit tests, integration tests, and quality standards.

## Testing Pyramid

```
    /\
   /  \     E2E Tests (few)
  /----\
 /      \   Integration Tests (some)
/--------\
/          \ Unit Tests (many)
------------
```

Our focus is on **unit tests** for business logic and **integration tests** for critical user flows.

## Test Levels

### Unit Tests

**Scope**: Individual functions, classes, or modules in isolation

**Characteristics**:
- Fast execution (< 100ms per test)
- No external dependencies (mocked)
- Deterministic results
- High coverage target (100% for core logic)

**Coverage Areas**:
- Queue/Lease behavior
- State machine transitions
- SSE sequencing
- Event envelope generation
- Serialization invariants

**Location**: `tests/unit/**/*.test.ts`

**Command**: `npm run test:unit`

---

### Integration Tests

**Scope**: Multiple components working together

**Characteristics**:
- Tests real component interactions
- May use test doubles for external services
- Slower than unit tests (seconds)
- Focus on critical paths

**Coverage Areas**:
- Run lifecycle (create → queue → run → complete)
- Tool execution with SSE streaming
- Daytona sandbox integration
- API endpoint flows

**Location**: `tests/integration/**/*.test.ts`

**Command**: `npm run test:integration`

---

### E2E Tests (Future)

**Scope**: Full system through public API

**Characteristics**:
- Tests from client perspective
- Uses real dependencies (or testcontainers)
- Slowest but highest confidence
- Limited to critical user journeys

**Coverage Areas** (planned):
- Complete user workflow
- Multi-client streaming
- Error recovery

## Test Organization

### Directory Structure

```
tests/
├── unit/
│   ├── orchestrator/          # Queue, lease, run manager tests
│   │   ├── queue.test.ts
│   │   ├── lease.test.ts
│   │   └── serialization.test.ts
│   ├── sse/                   # SSE-specific tests
│   │   ├── envelope.test.ts
│   │   ├── sequencer.test.ts
│   │   └── stream.test.ts
│   ├── tools/                 # Tool tests
│   ├── packs/                 # Pack loader tests
│   └── ...
├── integration/
│   ├── daytona-bash.test.ts   # Daytona execution
│   ├── tool-sse.test.ts       # Tool to SSE flow
│   └── health.test.ts         # Health endpoint
└── test-utils/
    ├── factories.ts           # Test data factories
    ├── assertions.ts          # Custom assertions
    └── mocks.ts               # Shared mocks
```

### Naming Conventions

**Files**: `{module-name}.test.ts`
- `queue.test.ts`
- `run-manager.test.ts`

**Describe blocks**: Match class/function hierarchy
```typescript
describe('InMemoryRunQueue', () => {
  describe('enqueue', () => {
    it('should add run and return position', () => {});
  });
});
```

**Test names**: Complete sentence describing behavior
```typescript
it('should return null for empty queue', () => {});
it('should reject acquisition when lease is active', () => {});
```

## Coverage Standards

### Target Coverage

| Module | Branch Coverage | Line Coverage |
|--------|----------------|---------------|
| Queue | 100% | 100% |
| Lease | 100% | 100% |
| SSE Core | 100% | 100% |
| Run Manager | > 90% | > 90% |
| Tools | > 80% | > 80% |
| Overall | > 80% | > 80% |

### Critical Paths (100% Coverage Required)

1. **Single Active Run Per User**: Queue + lease interaction
2. **SSE Sequence Monotonicity**: Seq generation and ordering
3. **State Transitions**: All valid and invalid transitions
4. **Terminal State Handling**: Cleanup on completion/failure

## Mocking Strategy

### What to Mock

**Always Mock**:
- External APIs (Daytona SDK)
- Database calls (in unit tests)
- Time-dependent code
- Random number generation

**Sometimes Mock**:
- Internal services (for unit tests)
- File system operations
- Network calls

**Never Mock** (in integration tests):
- Internal business logic
- Data structures
- Pure functions

### Mock Examples

**External Service (Daytona)**:
```typescript
vi.mock('../../src/sandbox/daytona-client.js', () => ({
  DaytonaClient: vi.fn().mockImplementation(() => ({
    createWorkspace: vi.fn().mockResolvedValue(mockWorkspace),
  })),
}));
```

**Time**:
```typescript
vi.useFakeTimers();
vi.setSystemTime(new Date('2024-01-15T10:00:00Z'));
```

**Module**:
```typescript
vi.mock('../../src/services/queue.js', async () => {
  const actual = await vi.importActual('../../src/services/queue.js');
  return {
    ...actual,
    runQueue: new MockRunQueue(),
  };
});
```

## Test Data Strategy

### Factories

Use factories to create consistent test data:

```typescript
// Create with defaults
const run = createRun();

// Override specific fields
const run = createRun({ userId: 'test-user', state: RunState.RUNNING });

// Specialized factories
const queuedRun = createQueuedRun('user-1');
const runningRun = createRunningRun('user-1');
```

### Fixtures

For complex test data, use fixtures:

```typescript
// tests/fixtures/runs.ts
export const sampleRun: Run = {
  id: 'run_123',
  userId: 'user_456',
  state: RunState.COMPLETED,
  // ...
};
```

### Property-Based Testing (Future)

Consider property-based testing for invariants:

```typescript
it('should maintain queue order for any sequence of operations', () => {
  fc.assert(
    fc.property(fc.array(queueOperation()), (ops) => {
      // Property: FIFO order is always maintained
    })
  );
});
```

## Assertions

### Standard Assertions

```typescript
expect(result).toBe(expected);           // Strict equality
expect(result).toEqual(expected);        // Deep equality
expect(result).toBeNull();               // Null check
expect(result).toBeUndefined();          // Undefined check
expect(result).toHaveLength(n);          // Array length
expect(result).toContain(item);          // Array contains
expect(result).toMatch(pattern);         // Regex match
expect(fn).toThrow();                    // Error thrown
expect(promise).resolves.toBe(value);    // Async resolve
expect(promise).rejects.toThrow();       // Async reject
```

### Custom Assertions

Create domain-specific assertions:

```typescript
// tests/test-utils/assertions.ts
export function assertSingleActiveRunPerUser(
  runs: Run[],
  userId: string
): void {
  const activeRuns = runs.filter(
    r => r.userId === userId && isActiveState(r.state)
  );
  expect(activeRuns.length).toBeLessThanOrEqual(1);
}

export function assertMonotonicSeq(
  events: SSEEventEnvelope[],
  strict = true
): void {
  for (let i = 1; i < events.length; i++) {
    if (strict) {
      expect(events[i].seq).toBe(events[i - 1].seq + 1);
    } else {
      expect(events[i].seq).toBeGreaterThan(events[i - 1].seq);
    }
  }
}
```

## Test Environments

### Local Development

```bash
# Fast feedback loop
npm run test:watch

# Run specific test
npm run test:unit -- tests/unit/queue.test.ts

# Debug mode
npm run test:unit -- --reporter=verbose --no-coverage
```

### CI/CD

```bash
# Full test suite
npm test

# With coverage report
npm run test:coverage

# Integration tests only
npm run test:integration
```

### Pre-commit

```bash
# Quick check before commit
npm run test:unit -- --run
```

## Test Quality Checklist

Before submitting PR, ensure:

- [ ] All new code has unit tests
- [ ] Critical paths have integration tests
- [ ] Tests are deterministic (no flakes)
- [ ] Tests clean up after themselves
- [ ] Mocks are reset between tests
- [ ] Test names are descriptive
- [ ] Coverage targets are met
- [ ] No `console.log` in tests (use `vi.spyOn(console, 'log')` if needed)
- [ ] No `.only` or `.skip` left in test files

## Anti-Patterns to Avoid

### Don't: Test Implementation Details

```typescript
// BAD: Testing private method
expect(service['internalCache'].size).toBe(1);

// GOOD: Testing behavior
expect(await service.getData()).toBe(expected);
```

### Don't: Test Multiple Things

```typescript
// BAD: Testing multiple behaviors
it('should work', () => {
  expect(a).toBe(1);
  expect(b).toBe(2);
  expect(c).toBe(3);
});

// GOOD: Separate tests
it('should set a to 1', () => ...);
it('should set b to 2', () => ...);
```

### Don't: Depend on Test Order

```typescript
// BAD: Tests depend on shared state
let counter = 0;
beforeEach(() => counter++);

// GOOD: Isolated tests
beforeEach(() => {
  counter = 0;
});
```

### Don't: Use Real Network/DB in Unit Tests

```typescript
// BAD: Real API call
const result = await fetch('https://api.example.com');

// GOOD: Mocked
vi.mocked(fetch).mockResolvedValue(mockResponse);
```

## Continuous Improvement

### Monitoring Test Health

- Track flaky tests and fix them
- Monitor test execution time
- Review coverage reports regularly
- Refactor tests as code evolves

### Test Refactoring

When to refactor tests:
- Duplicate setup code → Extract to `beforeEach` or factory
- Complex assertions → Create custom assertion helper
- Slow tests → Check for unnecessary dependencies
- Brittle tests → Reduce coupling to implementation

## References

- [Vitest Documentation](https://vitest.dev/)
- [Testing Best Practices](https://jestjs.io/docs/best-practices)
- [Unit Testing Guidelines](../../CODING_STANDARDS.md)
