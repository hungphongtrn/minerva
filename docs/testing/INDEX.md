# Testing Guide

## Overview

This guide explains how to run and write tests for the Minerva Orchestrator.

## Quick Start

### Run All Tests

```bash
cd services/orchestrator
npm test
```

### Run Unit Tests Only

```bash
npm run test:unit
```

### Run Integration Tests Only

```bash
npm run test:integration
```

### Run Tests in Watch Mode

```bash
npm run test:watch
```

## Test Structure

```
tests/
├── setup.ts                    # Global test setup
├── unit/                       # Unit tests
│   ├── orchestrator/           # Queue, lease, serialization tests
│   ├── sse/                    # SSE envelope, sequencer tests
│   ├── run-manager.test.ts     # Run manager tests
│   └── ...
├── integration/                # Integration tests
│   ├── daytona-bash.test.ts    # Daytona bash execution
│   └── tool-sse.test.ts        # Tool-to-SSE flow
└── test-utils/                 # Test utilities
    ├── factories.ts            # Test data factories
    └── assertions.ts           # Custom assertions
```

## Test Commands

### Specific Test Files

```bash
# Run specific test file
npm run test:unit -- tests/unit/queue.test.ts

# Run tests matching pattern
npm run test:unit -- --grep "should add a run"

# Run with coverage
npm run test:unit -- --coverage

# Run with verbose output
npm run test:unit -- --reporter=verbose
```

### Coverage Reports

```bash
# Generate coverage report
npm run test:coverage

# Coverage outputs:
# - console (text summary)
# - coverage/lcov-report/index.html (HTML report)
# - coverage/coverage-final.json (JSON data)
```

## Writing Tests

### Unit Test Template

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { MyService } from '../../src/services/my-service.js';

describe('MyService', () => {
  let service: MyService;

  beforeEach(() => {
    service = new MyService();
  });

  describe('methodName', () => {
    it('should do something specific', () => {
      const result = service.methodName('input');
      expect(result).toBe('expected output');
    });

    it('should handle edge case', () => {
      expect(() => service.methodName(null)).toThrow();
    });
  });
});
```

### Integration Test Template

```typescript
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

describe('Feature Integration', () => {
  beforeAll(async () => {
    // Setup test environment
  });

  afterAll(async () => {
    // Cleanup
  });

  it('should work end-to-end', async () => {
    // Test full flow
  });
});
```

### Using Test Utilities

```typescript
import { createRun } from '../test-utils/factories.js';
import { assertMonotonicSeq } from '../test-utils/assertions.js';

// Create test data
const run = createRun({ userId: 'test-user', state: RunState.QUEUED });

// Use custom assertions
const events = [...];
assertMonotonicSeq(events);
```

## Test Utilities

### Factories

Create consistent test data:

```typescript
// tests/test-utils/factories.ts
import { createRun, createQueuedRun, createRunningRun } from './factories.js';

const run1 = createRun();  // Default run
const run2 = createQueuedRun('user-1');  // Queued state
const run3 = createRunningRun('user-1'); // Running state
```

### Assertions

Custom assertions for common checks:

```typescript
// tests/test-utils/assertions.ts
import { 
  assertSingleActiveRunPerUser,
  assertMonotonicSeq,
  assertStreamTerminated 
} from './assertions.js';

// Assert queue/lease invariant
assertSingleActiveRunPerUser(runs, 'user-1');

// Assert SSE sequence
assertMonotonicSeq(events, true); // strict mode

// Assert stream termination
assertStreamTerminated(events, 'run_completed');
```

## Mocking

### Mock External Services

```typescript
import { vi } from 'vitest';

// Mock Daytona client
const mockClient = {
  createWorkspace: vi.fn().mockResolvedValue({ id: 'ws-123' }),
  executeCommand: vi.fn().mockResolvedValue({ exitCode: 0, stdout: 'ok' }),
};

// Mock with specific implementation
vi.mock('../../src/sandbox/daytona-client.js', () => ({
  DaytonaClient: vi.fn().mockImplementation(() => mockClient),
}));
```

### Mock Time

```typescript
// Freeze time
vi.useFakeTimers();
const now = new Date('2024-01-15T10:00:00Z');
vi.setSystemTime(now);

// Advance time
vi.advanceTimersByTime(1000);

// Restore
vi.useRealTimers();
```

## Environment Setup

### Test Environment Variables

Create `.env.test` for test-specific configuration:

```bash
# .env.test
NODE_ENV=test
DAYTONA_SERVER_URL=http://localhost:3000
DAYTONA_API_KEY=***
```

Load in test setup:

```typescript
// tests/setup.ts
import { config } from 'dotenv';
config({ path: '.env.test' });
```

## Best Practices

### Unit Tests

1. **Test one thing**: Each test should verify a single behavior
2. **Use descriptive names**: Test names should explain what is being tested
3. **Setup and teardown**: Use `beforeEach` to reset state
4. **Avoid dependencies**: Mock external services
5. **Test edge cases**: Include error conditions and boundaries

### Integration Tests

1. **Test real flows**: Verify components work together
2. **Clean up**: Always clean up resources in `afterAll`
3. **Timeout**: Set appropriate timeouts for long operations
4. **Environment**: Use test databases/sandboxes
5. **Idempotency**: Tests should be runnable multiple times

### Test Data

1. **Use factories**: Create test data consistently
2. **Avoid hardcoding**: Use generated values where possible
3. **Clear intent**: Make test data meaningful
4. **Cleanup**: Remove test data after tests

### Assertions

1. **Specific assertions**: Use specific matchers (`toBe`, `toEqual`)
2. **Meaningful messages**: Provide context when assertions fail
3. **Custom matchers**: Create domain-specific assertions
4. **Async assertions**: Use `resolves`/`rejects` for promises

## Debugging Tests

### VS Code Configuration

Add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "node",
      "request": "launch",
      "name": "Debug Unit Tests",
      "program": "${workspaceFolder}/node_modules/vitest/vitest.mjs",
      "args": ["run", "--reporter=verbose"],
      "cwd": "${workspaceFolder}/services/orchestrator",
      "console": "integratedTerminal"
    }
  ]
}
```

### Debug Logging

```typescript
// Add debug logs
console.log('Debug:', result);

// Or use debugger
debugger;
```

## Continuous Integration

Tests run automatically in CI:

```yaml
# .github/workflows/test.yml
- name: Run Tests
  run: |
    cd services/orchestrator
    npm ci
    npm run test:unit
    npm run test:integration
```

## Troubleshooting

### Common Issues

**Tests fail intermittently**
- Check for race conditions
- Use `beforeEach` to reset state
- Mock time-dependent code

**Integration tests timeout**
- Increase timeout: `--testTimeout 60000`
- Check external service availability
- Verify environment variables

**Coverage not accurate**
- Ensure all files are imported
- Check coverage configuration in `vitest.config.ts`

### Getting Help

- Check existing tests for patterns
- Review test utilities documentation
- Ask in #dev-testing channel
