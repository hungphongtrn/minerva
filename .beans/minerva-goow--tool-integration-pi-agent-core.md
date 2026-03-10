---
# minerva-goow
title: Tool Integration (pi-agent-core)
status: completed
type: task
priority: low
tags:
    - harvest
    - orchestrator-v0
    - verified
created_at: 2026-03-09T08:10:44Z
updated_at: 2026-03-10T04:45:36Z
parent: minerva-5rrj
blocked_by:
    - minerva-derz
    - minerva-ha33
---

## Requirements

- [x] 6.1 Define pi-agent-core tools for `bash`, `read`, and `write` with JSON-schema parameters
- [x] 6.2 Wire tool execution lifecycle events (`tool_execution_*`) into SSE
- [x] 6.3 Ensure tool errors surface deterministically as tool error results

## References

- **Proposal**: openspec/changes/orchestrator-v0/proposal.md
- **Design**: openspec/changes/orchestrator-v0/design.md
- **Tasks**: openspec/changes/orchestrator-v0/tasks.md



## Plan

📋 **Implementation Plan**: [docs/plans/orchestrator-v0/tool-integration-pi-agent-core.md](../../docs/plans/orchestrator-v0/tool-integration-pi-agent-core.md)



## Summary of Changes

### New Files Created
- **src/tools/types.ts** - Shared tool types including ToolError, ToolResult, ToolContext, and ToolEventEmitter interface
- **src/tools/index.ts** - Tool registry factory with dependency injection for Daytona adapter
- **src/sse/tool-events.ts** - ToolEventEmitter implementation that maps tool lifecycle events to SSE events
- **tests/integration/tool-sse.test.ts** - Integration tests verifying tool → SSE event flow

### Modified Files
- **src/tools/read.ts** - Updated to use Typebox JSON Schema, emit lifecycle events, and return structured ToolResult with deterministic error handling
- **src/tools/write.ts** - Updated to use Typebox JSON Schema, emit lifecycle events, and return structured ToolResult with deterministic error handling
- **src/tools/bash.ts** - Updated to use Typebox JSON Schema, emit lifecycle events with streaming updates, and return structured ToolResult
- **src/tools/read.test.ts** - Updated tests for new interface
- **src/tools/write.test.ts** - Updated tests for new interface
- **src/tools/bash.test.ts** - Updated tests for new interface
- **src/sse/index.ts** - Added exports for tool event emitters
- **package.json** - Added @sinclair/typebox dependency

### Key Implementation Details
1. **JSON Schema Parameters**: All tools now use Typebox for JSON Schema definitions with proper type inference
2. **Lifecycle Events**: Tools emit tool_execution_start, tool_execution_update (bash), and tool_execution_end events
3. **Deterministic Errors**: All errors are mapped to structured ToolError with codes (FILE_NOT_FOUND, PERMISSION_DENIED, TIMEOUT, CANCELLED, VALIDATION_ERROR, UNKNOWN_ERROR)
4. **Tool Result Pattern**: Tools return ToolResult<T> with success flag, data, and error fields instead of throwing
5. **SSE Integration**: createToolEventEmitter() creates an emitter that forwards events to SSE broadcaster with proper envelope format

### Test Coverage
- 27 unit tests across all three tools
- 11 integration tests for tool → SSE event flow
- All tests passing


## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-09

### Results
- All requirements met
- 27 unit tests across tools (read: 8, write: 7, bash: 12) - PASSING
- 11 integration tests for tool → SSE event flow - PASSING
- Code compiles without errors (tsc --noEmit)

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-10

### Results
- Verified `bash`, `read`, and `write` tools use JSON-schema definitions and structured result handling
- Verified `tool_execution_*` lifecycle events are wired into SSE flows
- Unit, integration, and typecheck verification passed for the tool integration work
