---
# minerva-ha33
title: SSE API
status: completed
type: task
priority: normal
tags:
    - harvest
    - orchestrator-v0
    - verified
created_at: 2026-03-09T10:49:40Z
updated_at: 2026-03-10T04:45:36Z
parent: minerva-5rrj
---

## Requirements

- [x] 3.1 Define the v0 SSE event envelope (`type`, `run_id`, `ts`, `seq`, payload)
- [x] 3.2 Implement SSE endpoint for a run with ordered event delivery and connection cleanup
- [x] 3.3 Map pi-agent-core message streaming events to SSE (text deltas, message lifecycle)

## Plan

**Implementation Plan**: [docs/plans/orchestrator-v0/sse-api.md](../../docs/plans/orchestrator-v0/sse-api.md)

## References

- **Proposal**: openspec/changes/orchestrator-v0/proposal.md
- **Design**: openspec/changes/orchestrator-v0/design.md
- **Tasks**: openspec/changes/orchestrator-v0/tasks.md

## Summary of Changes

Implemented the v0 SSE API for real-time run event streaming:

### New Files Created
-  - SSE event envelope types, event types, and payload definitions
-  - Event sequencer and envelope factory implementations
-  - Maps pi-agent-core events to SSE events
-  - SSE stream controller with connection management
-  - Bounded event buffer for replay/resilience
-  - NestJS service wrapping SSE functionality
-  - HTTP endpoint for run event streaming
-  - NestJS module configuration
-  - Module exports

### Modified Files
-  - Export SSE types for consumers
-  - Register SSE module
-  - Added @types/express dev dependency

### Features Implemented
- **Event Envelope (v0)**: , , , , payload structure
- **Event Types**: Orchestrator lifecycle (run_*), agent lifecycle (agent_*), turn lifecycle (turn_*), message streaming (message_*), tool execution (tool_execution_*)
- **Ordered Delivery**: Monotonically increasing sequence numbers per run
- **Connection Management**: Register/broadcast/close with cleanup on disconnect
- **Event Buffering**: Bounded buffer (1000 events) for replay on reconnect
- **SSE Endpoint**:  with replay support
- **Connection Events**: stream_connected event on client connect
- **Keep-Alive**: 30-second heartbeat to maintain connection
- **Auto-Cleanup**: Streams close automatically when run reaches terminal state
- **pi-agent-core Mapping**: All event types mapped (text deltas, message lifecycle, tool execution)

## Summary of Changes

Implemented the v0 SSE API for real-time run event streaming:

### New Files Created
- src/sse/types.ts - SSE event envelope types, event types, and payload definitions
- src/sse/envelope.ts - Event sequencer and envelope factory implementations
- src/sse/mapper.ts - Maps pi-agent-core events to SSE events
- src/sse/stream.ts - SSE stream controller with connection management
- src/sse/buffer.ts - Bounded event buffer for replay/resilience
- src/sse/sse.service.ts - NestJS service wrapping SSE functionality
- src/sse/sse.controller.ts - HTTP endpoint for run event streaming
- src/sse/sse.module.ts - NestJS module configuration
- src/sse/index.ts - Module exports

### Modified Files
- src/types/index.ts - Export SSE types for consumers
- src/app.module.ts - Register SSE module
- package.json - Added @types/express dev dependency

### Features Implemented
- Event Envelope v0 with type, run_id, ts, seq, payload
- Event Types: orchestrator lifecycle, agent lifecycle, turn lifecycle, message streaming, tool execution
- Ordered Delivery with monotonically increasing sequence numbers per run
- Connection Management with register/broadcast/close and cleanup
- Event Buffering with bounded buffer (1000 events) for replay
- SSE Endpoint GET /api/v0/runs/:runId/stream with replay support
- Connection Events stream_connected on client connect
- Keep-Alive with 30-second heartbeat
- Auto-Cleanup when run reaches terminal state
- pi-agent-core Mapping for all event types

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-09

### Results
- All requirements met
- Tests pass (60 SSE-specific tests across envelope, sequencer, stream, and tool-sse)
- Code compiles without errors
- Type checking passes

### Files Verified
**New Files:**
- services/orchestrator/src/sse/types.ts - SSE event envelope and payload types
- services/orchestrator/src/sse/envelope.ts - Event sequencer and envelope factory
- services/orchestrator/src/sse/mapper.ts - pi-agent-core event mapping
- services/orchestrator/src/sse/stream.ts - SSE stream controller
- services/orchestrator/src/sse/buffer.ts - Bounded event buffer (1000 events)
- services/orchestrator/src/sse/sse.service.ts - NestJS service wrapper
- services/orchestrator/src/sse/sse.controller.ts - HTTP endpoint for streaming
- services/orchestrator/src/sse/sse.module.ts - NestJS module
- services/orchestrator/src/sse/index.ts - Module exports
- services/orchestrator/src/sse/tool-events.ts - Tool event emitter

**Modified Files:**
- services/orchestrator/src/types/index.ts - Exports SSE types
- services/orchestrator/src/app.module.ts - Registers SSE module
- services/orchestrator/package.json - Has @types/express dependency

### Requirements Met
- ✅ 3.1 Define the v0 SSE event envelope (type, run_id, ts, seq, payload)
- ✅ 3.2 Implement SSE endpoint for a run with ordered event delivery and connection cleanup
- ✅ 3.3 Map pi-agent-core message streaming events to SSE (text deltas, message lifecycle)

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-10

### Results
- Verified SSE envelope, sequencing, buffering, endpoint behavior, and pi-agent-core event mapping
- Confirmed terminal-state cleanup and replay behavior
- `npm run build`, `npm run test:unit`, and `npm run test:integration` passed
