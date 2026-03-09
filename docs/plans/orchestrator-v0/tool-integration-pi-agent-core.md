# Tool Integration (pi-agent-core) - Implementation Plan

**Bean**: minerva-goow  
**Status**: Planned  
**Estimated Effort**: 2-3 days  
**Dependencies**: Section 5 (Daytona Sandbox Adapter)

---

## 1. Problem Statement and Goal

### Problem
The orchestrator needs to expose tools to pi-agent-core so the agent can execute filesystem operations and commands. These tools must:
1. Execute safely inside Daytona sandboxes (not on host)
2. Provide deterministic error handling
3. Stream lifecycle events to the UI via SSE
4. Follow pi-agent-core's tool contract with JSON Schema parameters

### Goal
Implement three pi-agent-core tools (`bash`, `read`, `write`) that delegate to the Daytona sandbox adapter, wire their lifecycle events to SSE, and ensure errors surface deterministically to the agent as structured tool results.

---

## 2. File-Level Changes

### New Files

| File | Description |
|------|-------------|
| `src/tools/types.ts` | Shared tool types: `ToolError`, `ToolResult`, `ToolContext` |
| `src/tools/read-tool.ts` | pi-agent-core tool definition for `read` with JSON schema |
| `src/tools/write-tool.ts` | pi-agent-core tool definition for `write` with JSON schema |
| `src/tools/bash-tool.ts` | pi-agent-core tool definition for `bash` with JSON schema |
| `src/tools/index.ts` | Tool registry and factory for creating tools with injected Daytona adapter |
| `src/sse/tool-events.ts` | Mapper from pi-agent-core tool events to SSE events |
| `src/tests/tools/*.test.ts` | Unit tests for each tool (validation, error cases) |
| `src/tests/integration/tool-sse.test.ts` | Integration test verifying tool events flow to SSE |

### Modified Files

| File | Changes |
|------|---------|
| `src/agent/worker.ts` | Inject tools into pi-agent-core agent; subscribe to tool events and forward to SSE stream |
| `src/sse/stream.ts` | Add handlers for tool_execution_* event types |
| `src/daytona/adapter.ts` | Ensure adapter methods return structured results suitable for tool integration |

---

## 3. Key Interfaces and Types

### Tool Types (`src/tools/types.ts`)

```typescript
// Tool execution context passed to all tools
interface ToolContext {
  sandboxId: string;
  runId: string;
  userId: string;
  daytonaAdapter: DaytonaAdapter;
}

// Structured error for deterministic error handling
interface ToolError {
  code: 'FILE_NOT_FOUND' | 'PERMISSION_DENIED' | 'COMMAND_FAILED' | 'VALIDATION_ERROR' | 'TIMEOUT' | 'CANCELLED';
  message: string;
  details?: Record<string, unknown>;
}

// Tool result wrapper for consistent return types
interface ToolResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: ToolError;
}
```

### Read Tool Schema (`src/tools/read-tool.ts`)

```typescript
import { Type } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";

export const readToolSchema = Type.Object({
  path: Type.String({ 
    description: "Absolute or relative path to the file to read" 
  }),
  encoding: Type.Optional(
    Type.Union([
      Type.Literal("utf-8"),
      Type.Literal("base64"),
      Type.Literal("latin1"),
    ], {
      description: "File encoding",
      default: "utf-8"
    })
  ),
  limit: Type.Optional(
    Type.Number({
      description: "Maximum bytes to read (for large files)",
      minimum: 1,
      maximum: 1024 * 1024, // 1MB
      default: 1024 * 1024
    })
  ),
});

export type ReadParams = Static<typeof readToolSchema>;

export interface ReadResult {
  content: string;
  size: number;
  encoding: string;
  truncated: boolean;
}
```

### Write Tool Schema (`src/tools/write-tool.ts`)

```typescript
export const writeToolSchema = Type.Object({
  path: Type.String({ 
    description: "Absolute or relative path to write the file" 
  }),
  content: Type.String({ 
    description: "Content to write" 
  }),
  encoding: Type.Optional(
    Type.Union([
      Type.Literal("utf-8"),
      Type.Literal("base64"),
    ], {
      description: "Content encoding",
      default: "utf-8"
    })
  ),
  append: Type.Optional(
    Type.Boolean({
      description: "Append to file instead of overwriting",
      default: false
    })
  ),
});

export type WriteParams = Static<typeof writeToolSchema>;

export interface WriteResult {
  path: string;
  bytesWritten: number;
  encoding: string;
}
```

### Bash Tool Schema (`src/tools/bash-tool.ts`)

```typescript
export const bashToolSchema = Type.Object({
  command: Type.String({ 
    description: "Shell command to execute" 
  }),
  cwd: Type.Optional(
    Type.String({ 
      description: "Working directory for command execution" 
    })
  ),
  timeout: Type.Optional(
    Type.Number({
      description: "Timeout in milliseconds (max 300000 = 5min)",
      minimum: 1000,
      maximum: 300000,
      default: 60000
    })
  ),
  env: Type.Optional(
    Type.Record(Type.String(), Type.String(), {
      description: "Environment variables to set"
    })
  ),
});

export type BashParams = Static<typeof bashToolSchema>;

export interface BashResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  duration: number; // ms
  truncated: boolean; // if output exceeded max size
}
```

### Tool Execution Event Mapping

| pi-agent-core Event | SSE Event Type | Payload Fields |
|---------------------|----------------|----------------|
| `tool_execution_start` | `tool_start` | `tool_call_id`, `tool_name`, `args` |
| `tool_execution_update` | `tool_progress` | `tool_call_id`, `partial_result` |
| `tool_execution_end` | `tool_end` | `tool_call_id`, `result`, `is_error`, `error_code?` |

SSE Event Envelope:
```typescript
interface SSEEvent {
  type: 'tool_start' | 'tool_progress' | 'tool_end' | /* ... other types */;
  run_id: string;
  ts: string; // ISO 8601
  seq: number; // Monotonic sequence number
  payload: unknown;
}
```

---

## 4. Test Strategy

### Unit Tests (`src/tests/tools/`)

| Test File | Coverage |
|-----------|----------|
| `read-tool.test.ts` | Schema validation, path traversal detection, encoding handling, large file truncation |
| `write-tool.test.ts` | Schema validation, directory creation, append mode, encoding round-trip |
| `bash-tool.test.ts` | Schema validation, timeout handling, exit code capture, env vars, cancellation |
| `tool-registry.test.ts` | Tool factory injects adapter correctly, all tools registered |

**Run command**: `npm test -- src/tests/tools/`

### Integration Tests (`src/tests/integration/`)

| Test File | Coverage |
|-----------|----------|
| `tool-sse.test.ts` | End-to-end: agent calls tool → events emitted → SSE receives correct sequence |
| `tool-error-flow.test.ts` | Verify tool errors map to SSE with `is_error: true` and correct error codes |

**Run command**: `npm run test:integration -- src/tests/integration/tool-sse.test.ts`

### Error Case Matrix

| Scenario | Expected Behavior |
|----------|-------------------|
| File not found (read) | `tool_execution_end` with `isError: true`, error code `FILE_NOT_FOUND` |
| Permission denied | `tool_execution_end` with `isError: true`, error code `PERMISSION_DENIED` |
| Command non-zero exit | `tool_execution_end` with `isError: false` (stderr in result), `exitCode > 0` |
| Command timeout | `tool_execution_end` with `isError: true`, error code `TIMEOUT` |
| Invalid JSON params | Tool never executes, pi-agent-core handles validation error |
| Cancellation | `tool_execution_end` with `isError: true`, error code `CANCELLED` |

---

## 5. Dependencies on Other Sections

| Section | Dependency | Impact |
|---------|------------|--------|
| 5.1 | Sandbox provisioning strategy | Tools need `sandboxId` from context |
| 5.2 | `bash` execution with streaming | `bash-tool.ts` execute() delegates to this |
| 5.3 | `read`/`write` operations | `read-tool.ts` and `write-tool.ts` delegate to this |
| 3.1 | SSE event envelope format | Tool events must follow same envelope |
| 3.2 | SSE endpoint implementation | Tool events feed into this stream |

**Critical path**: Section 5 (Daytona Adapter) must be complete before implementing tool execute() methods.

---

## 6. Reference Links

### OpenSpec Change Artifacts
- [Proposal](../../openspec/changes/orchestrator-v0/proposal.md) - Goals and capabilities
- [Design](../../openspec/changes/orchestrator-v0/design.md) - Decisions and constraints
- [Tasks](../../openspec/changes/orchestrator-v0/tasks.md) - Full task list

### Documentation
- [PI Agent Core - Events](../../docs/research/pi-agent-core/events.md) - Event model and sequences
- [PI Agent Core - Tools](../../docs/research/pi-agent-core/tools.md) - Tool definition patterns
- [Agent Runtime v0](../../docs/architecture/agent-runtime-v0.md) - Architecture notes
- [Coding Standards](../../docs/CODING_STANDARDS.md) - Code quality rules

### External References
- `@mariozechner/pi-agent-core` - Agent SDK
- `@sinclair/typebox` - JSON Schema validation
- Daytona TS SDK - Sandbox operations

---

## Implementation Checklist

- [ ] Create `src/tools/types.ts` with shared interfaces
- [ ] Implement `src/tools/read-tool.ts` with JSON schema
- [ ] Implement `src/tools/write-tool.ts` with JSON schema  
- [ ] Implement `src/tools/bash-tool.ts` with JSON schema
- [ ] Create `src/tools/index.ts` registry
- [ ] Implement `src/sse/tool-events.ts` mapper
- [ ] Wire tools into `src/agent/worker.ts`
- [ ] Add tool event handlers to `src/sse/stream.ts`
- [ ] Write unit tests for all tools
- [ ] Write integration test for tool → SSE flow
- [ ] Verify error handling matrix
