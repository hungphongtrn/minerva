# Implementation Plan: Daytona Sandbox Adapter

**Bean**: minerva-derz  
**Scope**: Section 5.x (Sandbox Execution)  
**Target**: TypeScript orchestrator sandbox integration

---

## 1. Problem Statement and Goal

### Problem
Minerva needs a secure, isolated execution environment for agent tools. All code execution and filesystem access must happen inside Daytona sandboxes, not on the host. We need to:

1. Provision and manage Daytona workspaces for agent runs
2. Execute `bash` commands with real-time stdout/stderr streaming
3. Safely perform `read` and `write` operations with path traversal protection
4. Ensure sandboxes have no general outbound network access (security invariant)

### Goal
Implement a Daytona Sandbox Adapter that:
- Provides a clean abstraction over the Daytona TypeScript SDK
- Supports both per-run (ephemeral) and per-user (warm) workspace strategies
- Streams command output in real-time for UI consumption
- Enforces workspace-root scoping and prevents path traversal attacks
- Validates network isolation configuration

### Success Criteria
- [ ] Sandboxes are provisioned efficiently (reuse or create as configured)
- [ ] `bash` tool streams stdout/stderr with exit status capture
- [ ] `read` and `write` operations are scoped to workspace root with path validation
- [ ] Path traversal attacks are prevented (e.g., `../../../etc/passwd`)
- [ ] Network isolation is verified and documented

---

## 2. File-Level Changes

### 2.1 New Files

| File | Purpose | Description |
|------|---------|-------------|
| `src/sandbox/adapter.ts` | Main adapter | High-level sandbox operations interface |
| `src/sandbox/daytona-client.ts` | SDK wrapper | Thin wrapper around `@daytonaio/sdk` |
| `src/sandbox/workspace-manager.ts` | Lifecycle | Workspace provisioning, reuse, and cleanup |
| `src/sandbox/strategy.ts` | Provisioning | Per-run vs per-user workspace strategies |
| `src/sandbox/execution.ts` | Command exec | Bash execution with streaming support |
| `src/sandbox/filesystem.ts` | File ops | Read/write with path validation |
| `src/sandbox/security.ts` | Security | Path traversal protection and validation |
| `src/sandbox/network.ts` | Network check | Validate sandbox network isolation |
| `src/sandbox/errors.ts` | Error types | Sandbox-specific error classes |
| `src/sandbox/types.ts` | Domain types | Workspace, ExecutionResult, FileOperation types |
| `src/tools/bash.ts` | Tool impl | `bash` tool implementation using adapter |
| `src/tools/read.ts` | Tool impl | `read` tool implementation using adapter |
| `src/tools/write.ts` | Tool impl | `write` tool implementation using adapter |

### 2.2 Modified Files

| File | Changes |
|------|---------|
| `src/config/index.ts` | Add Daytona connection and sandbox config |
| `src/types/index.ts` | Export sandbox types |
| `src/orchestrator/worker.ts` | Inject sandbox adapter into agent loop |
| `src/services/sandbox-service.ts` | Implement ISandboxService using adapter |

---

## 3. Key Interfaces and Types

### 3.1 Sandbox Adapter Interface

```typescript
// src/sandbox/adapter.ts

export interface ISandboxAdapter {
  // Workspace lifecycle
  getOrCreateWorkspace(userId: string, strategy: WorkspaceStrategy): Promise<Workspace>;
  destroyWorkspace(workspaceId: string): Promise<void>;
  
  // Execution
  execute(
    workspaceId: string, 
    command: string, 
    options?: ExecutionOptions
  ): AsyncIterable<ExecutionChunk>;
  
  // Filesystem
  readFile(workspaceId: string, path: string): Promise<string>;
  writeFile(workspaceId: string, path: string, content: string): Promise<void>;
  
  // Validation
  validateNetworkIsolation(workspaceId: string): Promise<NetworkCheckResult>;
}

export interface ExecutionOptions {
  timeoutMs?: number;
  workingDir?: string;
  env?: Record<string, string>;
  signal?: AbortSignal;
}

export interface ExecutionChunk {
  type: 'stdout' | 'stderr' | 'exit';
  data: string | number;  // string for output, number for exit code
  timestamp: number;
}

export interface ExecutionResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}
```

### 3.2 Workspace Types

```typescript
// src/sandbox/types.ts

export enum WorkspaceStrategy {
  PER_RUN = 'per_run',      // Clean workspace for each run (v0 default)
  PER_USER = 'per_user',    // Reuse workspace for same user (warm)
}

export interface Workspace {
  id: string;
  userId: string;
  createdAt: Date;
  lastUsedAt: Date;
  isReused: boolean;
  rootPath: string;         // Absolute path to workspace root in sandbox
}

export interface WorkspaceConfig {
  image: string;
  resources: {
    cpu: number;            // CPU cores
    memory: string;         // Memory limit (e.g., "2Gi")
    disk: string;           // Disk limit (e.g., "10Gi")
  };
  network: {
    outbound: 'none' | 'restricted' | 'full';  // v0: 'none'
  };
  timeout: {
    idleMinutes: number;    // Auto-destroy after idle
    maxLifetimeMinutes: number;
  };
}
```

### 3.3 File Operation Types

```typescript
// src/sandbox/filesystem.ts

export interface FileReadOptions {
  encoding?: BufferEncoding;
  maxSize?: number;         // Prevent reading huge files
}

export interface FileWriteOptions {
  encoding?: BufferEncoding;
  createDirs?: boolean;     // Auto-create parent directories
  mode?: number;            // File permissions
}

export interface PathValidationResult {
  isValid: boolean;
  normalizedPath: string;
  error?: string;
}
```

### 3.4 Tool Implementations

```typescript
// src/tools/bash.ts

import { AgentTool } from '@mariozechner/pi-agent-core';
import { Type } from '@sinclair/typebox';

export const createBashTool = (adapter: ISandboxAdapter): AgentTool => ({
  name: 'bash',
  label: 'Execute Command',
  description: 'Execute a bash command in the sandbox and stream output',
  parameters: Type.Object({
    command: Type.String({ description: 'Command to execute' }),
    timeout: Type.Optional(Type.Number({ description: 'Timeout in seconds' })),
  }),
  execute: async (toolCallId, params, signal, onUpdate) => {
    // Get workspace from context (injected by worker)
    const workspaceId = getCurrentWorkspaceId();
    
    const chunks: string[] = [];
    
    for await (const chunk of adapter.execute(workspaceId, params.command, {
      timeoutMs: params.timeout ? params.timeout * 1000 : undefined,
      signal,
    })) {
      if (chunk.type === 'stdout' || chunk.type === 'stderr') {
        chunks.push(String(chunk.data));
        onUpdate?.({
          content: [{ type: 'text', text: String(chunk.data) }],
          details: { stream: chunk.type },
        });
      } else if (chunk.type === 'exit') {
        const exitCode = Number(chunk.data);
        if (exitCode !== 0) {
          throw new Error(`Command failed with exit code ${exitCode}`);
        }
      }
    }
    
    return {
      content: [{ type: 'text', text: chunks.join('') }],
      details: { command: params.command },
    };
  },
});
```

```typescript
// src/tools/read.ts

export const createReadTool = (adapter: ISandboxAdapter): AgentTool => ({
  name: 'read',
  label: 'Read File',
  description: 'Read contents of a file in the sandbox workspace',
  parameters: Type.Object({
    path: Type.String({ description: 'File path (relative to workspace root)' }),
  }),
  execute: async (toolCallId, params) => {
    const workspaceId = getCurrentWorkspaceId();
    const content = await adapter.readFile(workspaceId, params.path);
    
    return {
      content: [{ type: 'text', text: content }],
      details: { path: params.path, size: content.length },
    };
  },
});
```

```typescript
// src/tools/write.ts

export const createWriteTool = (adapter: ISandboxAdapter): AgentTool => ({
  name: 'write',
  label: 'Write File',
  description: 'Write content to a file in the sandbox workspace',
  parameters: Type.Object({
    path: Type.String({ description: 'File path (relative to workspace root)' }),
    content: Type.String({ description: 'Content to write' }),
  }),
  execute: async (toolCallId, params) => {
    const workspaceId = getCurrentWorkspaceId();
    await adapter.writeFile(workspaceId, params.path, params.content);
    
    return {
      content: [{ type: 'text', text: `File written: ${params.path}` }],
      details: { path: params.path, size: params.content.length },
    };
  },
});
```

### 3.5 Security Utilities

```typescript
// src/sandbox/security.ts

/**
 * Validate and normalize a user-provided path.
 * 
 * Rules:
 * 1. Path must be relative (no leading /)
 * 2. Path must not escape workspace root (no ../..)
 * 3. Path must not contain null bytes
 * 4. Path is normalized (resolve . and .. safely)
 */
export function validatePath(
  userPath: string, 
  workspaceRoot: string
): PathValidationResult {
  // Check for null bytes
  if (userPath.includes('\0')) {
    return { isValid: false, normalizedPath: '', error: 'Path contains null bytes' };
  }
  
  // Check for absolute paths
  if (userPath.startsWith('/')) {
    return { isValid: false, normalizedPath: '', error: 'Absolute paths not allowed' };
  }
  
  // Normalize the path
  const normalized = path.normalize(userPath);
  
  // Check for traversal attempts after normalization
  if (normalized.startsWith('..')) {
    return { isValid: false, normalizedPath: '', error: 'Path traversal detected' };
  }
  
  // Final resolved path must still be under workspace root
  const resolvedPath = path.join(workspaceRoot, normalized);
  const relativeToRoot = path.relative(workspaceRoot, resolvedPath);
  
  if (relativeToRoot.startsWith('..') || relativeToRoot.startsWith('/')) {
    return { isValid: false, normalizedPath: '', error: 'Path escapes workspace root' };
  }
  
  return { isValid: true, normalizedPath: normalized };
}
```

---

## 4. Test Strategy

### 4.1 Unit Tests

| Module | Test Coverage | Test File |
|--------|--------------|-----------|
| Path validation | Traversal attacks, edge cases, normalization | `src/sandbox/security.test.ts` |
| Workspace strategy | Per-run vs per-user logic | `src/sandbox/strategy.test.ts` |
| Command streaming | Chunk parsing, exit code handling | `src/sandbox/execution.test.ts` |
| Tool implementations | Parameter validation, error handling | `src/tools/bash.test.ts`, `src/tools/read.test.ts`, `src/tools/write.test.ts` |

**Test Commands:**
```bash
# Run sandbox tests
npm test -- src/sandbox/

# Run tool tests
npm test -- src/tools/

# Run with coverage
npm test -- --coverage src/sandbox/ src/tools/
```

### 4.2 Integration Tests

| Scenario | Test File | Description |
|----------|-----------|-------------|
| Daytona connection | `tests/integration/daytona-connection.test.ts` | SDK connectivity and workspace creation |
| Command execution | `tests/integration/bash-execution.test.ts` | Full bash flow with streaming |
| File operations | `tests/integration/filesystem.test.ts` | Read/write roundtrip |
| Path security | `tests/integration/path-traversal.test.ts` | Attempt traversal attacks |
| Network isolation | `tests/integration/network-isolation.test.ts` | Verify no outbound network |

**Integration Test Commands:**
```bash
# Requires Daytona server running or testcontainers
npm run test:integration -- tests/integration/daytona-connection.test.ts

# Run all sandbox integration tests
npm run test:integration -- tests/integration/*.test.ts
```

### 4.3 Security Test Cases

Path traversal attempts to test:
```typescript
const maliciousPaths = [
  '../../../etc/passwd',
  '..\\..\\windows\\system32\\config\\sam',
  'foo/../../../etc/passwd',
  './../../etc/passwd',
  'foo/bar/../../../../etc/passwd',
  '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',  // URL encoded
  '..\x00/../../etc/passwd',  // Null byte injection
];
```

### 4.4 Test Utilities

Create `src/test-utils/sandbox-mocks.ts`:
- `createMockAdapter(): ISandboxAdapter`
- `createMockWorkspace(overrides?: Partial<Workspace>): Workspace`
- `createExecutionStream(chunks: ExecutionChunk[]): AsyncIterable<ExecutionChunk>`

---

## 5. Dependencies on Other Sections

| Dependency | Section | Impact |
|------------|---------|--------|
| Project setup | 1.x | Requires TypeScript project, Daytona SDK installed |
| Run model | 2.x | Needs workspace ID from run context |
| Agent worker | 4.x | Worker injects adapter and workspace context into tools |
| Config | 1.x | Reads Daytona connection settings |

**Dependency Graph:**
```
Daytona Sandbox Adapter (this section)
    ↑ depends on
Project Setup (TypeScript, SDK)
    ↑
Config (Daytona credentials)
    ↓
Run Model + Agent Worker
    (injects workspace context)
```

**Note**: This section is blocked by project setup (minerva-eegh) and has a sibling dependency on run model (minerva-5rrj child beans).

---

## 6. Implementation Phases

### Phase 1: Core Adapter and Types (5.1)
- [ ] Define all sandbox types and interfaces
- [ ] Implement Daytona SDK wrapper
- [ ] Create workspace provisioning strategies
- [ ] Add error handling

### Phase 2: Execution and Streaming (5.2)
- [ ] Implement bash execution with streaming
- [ ] Add stdout/stderr chunking
- [ ] Capture exit status
- [ ] Handle timeouts and cancellation

### Phase 3: Filesystem with Security (5.3)
- [ ] Implement read/write operations
- [ ] Add path traversal protection
- [ ] Workspace-root scoping
- [ ] File size limits

### Phase 4: Tool Integration (5.1-5.3 integration)
- [ ] Create bash tool implementation
- [ ] Create read tool implementation
- [ ] Create write tool implementation
- [ ] Wire tools into agent worker

### Phase 5: Network Validation (5.4)
- [ ] Implement network isolation check
- [ ] Document Daytona network configuration
- [ ] Add integration tests for network restrictions

---

## 7. Configuration

Add to `src/config/index.ts`:

```typescript
export interface SandboxConfig {
  strategy: WorkspaceStrategy;
  daytona: {
    serverUrl: string;
    apiKey: string;
    target: string;
  };
  workspace: {
    image: string;
    resources: {
      cpu: number;
      memory: string;
      disk: string;
    };
    network: {
      outbound: 'none' | 'restricted' | 'full';
    };
    timeouts: {
      idleMinutes: number;
      maxLifetimeMinutes: number;
      commandTimeoutMs: number;
    };
  };
  security: {
    maxFileSize: number;      // Bytes
    allowedPaths: string[];   // Whitelist (optional)
  };
}
```

Environment variables:
```bash
# .env.example additions
DAYTONA_WORKSPACE_STRATEGY=per_run
DAYTONA_WORKSPACE_IMAGE=daytonaio/workspace:latest
DAYTONA_WORKSPACE_CPU=2
DAYTONA_WORKSPACE_MEMORY=4Gi
DAYTONA_WORKSPACE_NETWORK=none
DAYTONA_COMMAND_TIMEOUT_MS=300000
DAYTONA_MAX_FILE_SIZE=10485760  # 10MB
```

---

## 8. Reference Links

### Documentation
- [Project Scope](../../PROJECT.md) - What Minerva is building
- [Process Workflow](../../process/markdown-beans-workflow.md) - Markdown-first planning and bean tracking expectations
- [Architecture v0](../../architecture/agent-runtime-v0.md) - Component overview and execution model
- [Sandbox Execution Reference](../../specs/sandbox-execution.md) - Plain-markdown sandbox constraints
- [Coding Standards](../../CODING_STANDARDS.md) - Code quality and dependency rules

### Research
- [pi-agent-core Tools](../../research/pi-agent-core/tools.md) - Tool implementation patterns
- [pi-agent-core Events](../../research/pi-agent-core/events.md) - Event streaming for tool execution

### Related Plans
- [Project Setup](../orchestrator-v0/project-setup.md) - TypeScript project scaffolding
- [Run Model](../orchestrator-v0/run-model-scheduling.md) - Run lifecycle and workspace context

### External Dependencies
- [@daytonaio/sdk](https://www.npmjs.com/package/@daytonaio/sdk) - Daytona TypeScript SDK
- [@mariozechner/pi-agent-core](https://www.npmjs.com/package/@mariozechner/pi-agent-core) - Agent loop and tools

---

## 9. Open Questions / Notes

1. **Workspace reuse cleanup**: When using PER_USER strategy, how aggressively should we clean up workspace state between runs? Should we provide a "reset" option?

2. **File encoding**: Should we auto-detect file encoding or always use UTF-8? What about binary files?

3. **Large file handling**: What's the maximum file size we should allow for read/write? Current plan: 10MB configurable.

4. **Network check implementation**: Daytona may not expose a direct API to verify network isolation. We may need to:
   - Run a test command inside the sandbox (e.g., `curl --connect-timeout 5 google.com`)
   - Trust the Daytona configuration and document the requirement
   - Validate at workspace creation time

5. **Warm workspace security**: PER_USER strategy keeps a sandbox warm - this could potentially leak state between runs. We should document this trade-off and consider optional workspace reset.

6. **Daytona SDK version**: Pin to a specific version to avoid breaking changes. Current latest: check npm registry.

---

## 10. Security Checklist

Before marking complete:
- [ ] Path traversal tests pass (all malicious paths blocked)
- [ ] Absolute path requests are rejected
- [ ] Null byte injection is blocked
- [ ] File size limits are enforced
- [ ] Network isolation is verified (no outbound connections)
- [ ] Workspace boundaries are respected
- [ ] No secrets are passed to sandbox via environment
- [ ] Command injection is mitigated (shell escaping)

---

*Plan created: 2026-03-09*  
*Status: Ready for implementation (blocked by project setup)*
