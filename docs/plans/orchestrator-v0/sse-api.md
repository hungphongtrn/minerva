# SSE API Implementation Plan

## 1. Problem Statement and Goal

### Problem
The orchestrator needs to stream real-time agent execution progress to UI clients. The pi-agent-core SDK provides rich event streaming, but there's no defined protocol for:
- Structuring events for external SSE consumers (envelope format, sequencing, ordering guarantees)
- Maintaining SSE connections with proper backpressure and cleanup
- Mapping pi-agent-core's internal event model to a stable public SSE contract

### Goal
Implement a robust SSE API that:
- Defines a stable v0 event envelope with sequencing metadata (`type`, `run_id`, `ts`, `seq`, payload)
- Provides an SSE endpoint per run with ordered event delivery and connection lifecycle management
- Maps pi-agent-core message streaming events (text deltas, message lifecycle, tool execution) to SSE with minimal transformation
- Handles connection cleanup on client disconnect and run completion

### Success Criteria
- [ ] SSE event envelope is defined and versioned (v0)
- [ ] Events are delivered in order with monotonically increasing `seq` numbers
- [ ] Text deltas from assistant messages stream in real-time
- [ ] Tool execution lifecycle events are forwarded to SSE
- [ ] Connections are properly cleaned up on disconnect or run completion
- [ ] Stream terminates cleanly when run reaches terminal state

---

## 2. File-Level Changes

### 2.1 New Files

| File | Purpose | Description |
|------|---------|-------------|
| `src/sse/types.ts` | Event types | SSE event envelope, event types, payload definitions |
| `src/sse/envelope.ts` | Event envelope | Event sequencing, timestamp generation, envelope factory |
| `src/sse/mapper.ts` | Event mapping | Map pi-agent-core events to SSE events |
| `src/sse/stream.ts` | Stream management | SSE stream controller with backpressure and cleanup |
| `src/sse/buffer.ts` | Event buffering | Bounded event buffer for replay/resilience |
| `src/sse/connection.ts` | Connection mgmt | Client connection tracking and cleanup |
| `src/api/routes/sse.ts` | SSE endpoint | HTTP endpoint for run event streaming |
| `src/api/middleware/sse.ts` | SSE middleware | Headers, keep-alive, connection handling |

### 2.2 Modified Files

| File | Changes |
|------|---------|
| `src/api/server.ts` | Register SSE route, configure timeout handling |
| `src/orchestrator/worker.ts` | Wire pi-agent-core event stream to SSE broadcaster |
| `src/orchestrator/run-manager.ts` | Emit orchestrator-level lifecycle events |
| `src/types/index.ts` | Export SSE types for consumers |

---

## 3. Key Interfaces and Types

### 3.1 SSE Event Envelope (v0)

```typescript
// src/sse/types.ts

/**
 * SSE Event Envelope v0
 * 
 * All SSE events share this envelope structure for consistent
 * client consumption and debugging.
 */
export interface SSEEventEnvelope<TPayload = unknown> {
  /** Event type discriminator */
  type: SSEEventType;
  
  /** Run identifier (ULID) */
  run_id: string;
  
  /** Event timestamp (ISO 8601 UTC) */
  ts: string;
  
  /** Monotonically increasing sequence number per run */
  seq: number;
  
  /** Event-specific payload */
  payload: TPayload;
}

/** SSE Event Types - aligned with pi-agent-core + orchestrator extensions */
export type SSEEventType =
  // Orchestrator lifecycle
  | 'run_queued'
  | 'run_started'
  | 'run_completed'
  | 'run_failed'
  | 'run_cancelled'
  | 'run_timed_out'
  
  // pi-agent-core agent lifecycle
  | 'agent_start'
  | 'agent_end'
  
  // pi-agent-core turn lifecycle
  | 'turn_start'
  | 'turn_end'
  
  // pi-agent-core message lifecycle
  | 'message_start'
  | 'message_update'
  | 'message_end'
  
  // pi-agent-core tool execution
  | 'tool_execution_start'
  | 'tool_execution_update'
  | 'tool_execution_end';

/** Event type categorization for filtering/routing */
export type SSEEventCategory = 
  | 'orchestrator'  // Orchestrator-level lifecycle
  | 'agent'         // Agent loop events
  | 'turn'          // Turn-level events
  | 'message'       // Message streaming
  | 'tool';         // Tool execution
```

### 3.2 Event Payloads

```typescript
// src/sse/types.ts

/** Base payload fields for all events */
interface BasePayload {
  // Reserved for future common fields
}

/** Orchestrator: Run queued */
export interface RunQueuedPayload extends BasePayload {
  queue_position: number;
  estimated_start?: string;  // ISO timestamp
}

/** Orchestrator: Run started */
export interface RunStartedPayload extends BasePayload {
  started_at: string;
  sandbox_id?: string;
}

/** Orchestrator: Run terminal states */
export interface RunCompletedPayload extends BasePayload {
  completed_at: string;
  duration_ms: number;
}

export interface RunFailedPayload extends BasePayload {
  failed_at: string;
  error: string;
  error_code?: string;
}

export interface RunCancelledPayload extends BasePayload {
  cancelled_at: string;
  reason?: string;
}

export interface RunTimedOutPayload extends BasePayload {
  timed_out_at: string;
  timeout_duration_ms: number;
}

/** pi-agent-core: Agent lifecycle */
export interface AgentStartPayload extends BasePayload {
  // No additional fields
}

export interface AgentEndPayload extends BasePayload {
  messages: unknown[];  // AgentMessage[] serialized
}

/** pi-agent-core: Turn lifecycle */
export interface TurnStartPayload extends BasePayload {
  turn_number: number;
}

export interface TurnEndPayload extends BasePayload {
  turn_number: number;
  message: unknown;     // AgentMessage serialized
  tool_results: unknown[];
}

/** pi-agent-core: Message lifecycle */
export interface MessageStartPayload extends BasePayload {
  message: unknown;     // AgentMessage serialized
}

export interface MessageUpdatePayload extends BasePayload {
  message: unknown;     // Partial AgentMessage
  delta_type: 'text_delta' | 'thinking_delta' | 'toolcall_start' | 'toolcall_delta';
  delta: unknown;       // Type-specific delta
}

export interface MessageEndPayload extends BasePayload {
  message: unknown;     // Final AgentMessage
}

/** pi-agent-core: Tool execution */
export interface ToolExecutionStartPayload extends BasePayload {
  tool_call_id: string;
  tool_name: string;
  args: Record<string, unknown>;
}

export interface ToolExecutionUpdatePayload extends BasePayload {
  tool_call_id: string;
  tool_name: string;
  partial_result: {
    type: 'stdout' | 'stderr' | 'progress';
    data: string;
  };
}

export interface ToolExecutionEndPayload extends BasePayload {
  tool_call_id: string;
  tool_name: string;
  result: unknown;
  is_error: boolean;
  duration_ms: number;
}
```

### 3.3 Event Envelope Factory

```typescript
// src/sse/envelope.ts

export interface EventSequencer {
  /** Get next sequence number for a run */
  next(runId: string): number;
  
  /** Get current sequence number for a run */
  current(runId: string): number;
  
  /** Reset sequence for a run (on reconnect/resume) */
  reset(runId: string, startAt?: number): void;
}

export interface EnvelopeFactory {
  /** Create an envelope with auto-incrementing seq */
  create<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload
  ): SSEEventEnvelope<TPayload>;
  
  /** Create envelope at specific seq (for replay) */
  createAt<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload,
    seq: number,
    ts: string
  ): SSEEventEnvelope<TPayload>;
}

/** In-memory sequencer implementation (v0) */
export class MemoryEventSequencer implements EventSequencer {
  private counters = new Map<string, number>();
  
  next(runId: string): number {
    const current = this.counters.get(runId) ?? 0;
    const next = current + 1;
    this.counters.set(runId, next);
    return next;
  }
  
  current(runId: string): number {
    return this.counters.get(runId) ?? 0;
  }
  
  reset(runId: string, startAt = 0): void {
    this.counters.set(runId, startAt);
  }
  
  /** Cleanup when run ends */
  cleanup(runId: string): void {
    this.counters.delete(runId);
  }
}
```

### 3.4 pi-agent-core to SSE Mapper

```typescript
// src/sse/mapper.ts

import type { AgentEvent } from '@mariozechner/pi-agent-core';
import type { SSEEventEnvelope, SSEEventType } from './types.js';

export interface EventMapper {
  /** Map a pi-agent-core event to SSE envelope(s) */
  map(agentEvent: AgentEvent, runId: string): SSEEventEnvelope | null;
  
  /** Map orchestrator lifecycle event */
  mapOrchestratorEvent(
    runId: string,
    type: 'run_queued' | 'run_started' | 'run_completed' | 'run_failed' | 'run_cancelled' | 'run_timed_out',
    payload: unknown
  ): SSEEventEnvelope;
}

/** 
 * Default mapper - 1:1 mapping with minimal transformation
 * 
 * Maps pi-agent-core events directly to SSE with same event names
 * to maintain consistency between internal and external APIs.
 */
export class DefaultEventMapper implements EventMapper {
  constructor(private sequencer: EventSequencer) {}
  
  map(agentEvent: AgentEvent, runId: string): SSEEventEnvelope | null {
    const seq = this.sequencer.next(runId);
    const ts = new Date().toISOString();
    
    switch (agentEvent.type) {
      case 'agent_start':
        return {
          type: 'agent_start',
          run_id: runId,
          ts,
          seq,
          payload: {}
        };
        
      case 'agent_end':
        return {
          type: 'agent_end',
          run_id: runId,
          ts,
          seq,
          payload: { messages: agentEvent.messages }
        };
        
      case 'turn_start':
        return {
          type: 'turn_start',
          run_id: runId,
          ts,
          seq,
          payload: { turn_number: agentEvent.turnNumber ?? 0 }
        };
        
      case 'turn_end':
        return {
          type: 'turn_end',
          run_id: runId,
          ts,
          seq,
          payload: {
            turn_number: agentEvent.turnNumber ?? 0,
            message: agentEvent.message,
            tool_results: agentEvent.toolResults
          }
        };
        
      case 'message_start':
        return {
          type: 'message_start',
          run_id: runId,
          ts,
          seq,
          payload: { message: agentEvent.message }
        };
        
      case 'message_update':
        return {
          type: 'message_update',
          run_id: runId,
          ts,
          seq,
          payload: {
            message: agentEvent.message,
            delta_type: agentEvent.assistantMessageEvent.type,
            delta: agentEvent.assistantMessageEvent
          }
        };
        
      case 'message_end':
        return {
          type: 'message_end',
          run_id: runId,
          ts,
          seq,
          payload: { message: agentEvent.message }
        };
        
      case 'tool_execution_start':
        return {
          type: 'tool_execution_start',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId,
            tool_name: agentEvent.toolName,
            args: agentEvent.args
          }
        };
        
      case 'tool_execution_update':
        return {
          type: 'tool_execution_update',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId,
            tool_name: agentEvent.toolName,
            partial_result: agentEvent.partialResult
          }
        };
        
      case 'tool_execution_end':
        return {
          type: 'tool_execution_end',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId,
            tool_name: agentEvent.toolName,
            result: agentEvent.result,
            is_error: agentEvent.isError,
            duration_ms: agentEvent.durationMs
          }
        };
        
      default:
        // Unknown event type - log and skip
        console.warn(`Unknown agent event type: ${(agentEvent as {type: string}).type}`);
        return null;
    }
  }
  
  mapOrchestratorEvent(
    runId: string,
    type: SSEEventType,
    payload: unknown
  ): SSEEventEnvelope {
    return {
      type,
      run_id: runId,
      ts: new Date().toISOString(),
      seq: this.sequencer.next(runId),
      payload
    };
  }
}
```

### 3.5 SSE Stream Controller

```typescript
// src/sse/stream.ts

import type { SSEEventEnvelope } from './types.js';

export interface SSEStream {
  /** Write event to stream */
  write(event: SSEEventEnvelope): void;
  
  /** Close stream gracefully */
  close(): void;
  
  /** Check if stream is still open */
  isOpen(): boolean;
  
  /** Get client IP for logging */
  getClientInfo(): { ip: string; userAgent?: string };
}

export interface SSEStreamController {
  /** Register a new SSE connection for a run */
  register(runId: string, stream: SSEStream): () => void;
  
  /** Broadcast event to all connected clients for a run */
  broadcast(runId: string, event: SSEEventEnvelope): void;
  
  /** Close all connections for a run */
  closeRun(runId: string): void;
  
  /** Get connection count for a run */
  getConnectionCount(runId: string): number;
  
  /** Get total connections across all runs */
  getTotalConnections(): number;
}

/** 
 * In-memory stream controller (v0)
 * 
 * Maintains mapping of runId -> Set of active streams
 * Handles cleanup on disconnect and run completion.
 */
export class MemorySSEStreamController implements SSEStreamController {
  private streams = new Map<string, Set<SSEStream>>();
  
  register(runId: string, stream: SSEStream): () => void {
    if (!this.streams.has(runId)) {
      this.streams.set(runId, new Set());
    }
    
    const runStreams = this.streams.get(runId)!;
    runStreams.add(stream);
    
    // Return cleanup function
    return () => {
      runStreams.delete(stream);
      if (runStreams.size === 0) {
        this.streams.delete(runId);
      }
      
      // Close stream if still open
      if (stream.isOpen()) {
        stream.close();
      }
    };
  }
  
  broadcast(runId: string, event: SSEEventEnvelope): void {
    const runStreams = this.streams.get(runId);
    if (!runStreams) return;
    
    const data = JSON.stringify(event);
    const deadStreams: SSEStream[] = [];
    
    for (const stream of runStreams) {
      try {
        if (stream.isOpen()) {
          stream.write(event);
        } else {
          deadStreams.push(stream);
        }
      } catch (err) {
        // Stream error - mark for cleanup
        deadStreams.push(stream);
      }
    }
    
    // Cleanup dead streams
    for (const dead of deadStreams) {
      runStreams.delete(dead);
      try {
        dead.close();
      } catch {
        // Ignore close errors
      }
    }
    
    if (runStreams.size === 0) {
      this.streams.delete(runId);
    }
  }
  
  closeRun(runId: string): void {
    const runStreams = this.streams.get(runId);
    if (!runStreams) return;
    
    for (const stream of runStreams) {
      try {
        stream.close();
      } catch {
        // Ignore close errors
      }
    }
    
    this.streams.delete(runId);
  }
  
  getConnectionCount(runId: string): number {
    return this.streams.get(runId)?.size ?? 0;
  }
  
  getTotalConnections(): number {
    let total = 0;
    for (const runStreams of this.streams.values()) {
      total += runStreams.size;
    }
    return total;
  }
}
```

### 3.6 Bounded Event Buffer

```typescript
// src/sse/buffer.ts

import type { SSEEventEnvelope } from './types.js';

export interface EventBuffer {
  /** Add event to buffer */
  push(event: SSEEventEnvelope): void;
  
  /** Get events from seq (inclusive) to present */
  getFrom(seq: number): SSEEventEnvelope[];
  
  /** Get all buffered events */
  getAll(): SSEEventEnvelope[];
  
  /** Clear buffer for a run */
  clear(runId: string): void;
  
  /** Get buffer size for a run */
  size(runId: string): number;
}

/**
 * Bounded event buffer for replay/resilience
 * 
 * Keeps last N events per run for client reconnect scenarios.
 * Events are evicted in FIFO order when buffer is full.
 */
export class BoundedEventBuffer implements EventBuffer {
  private buffers = new Map<string, SSEEventEnvelope[]>();
  
  constructor(private maxSize: number = 1000) {}
  
  push(event: SSEEventEnvelope): void {
    let buffer = this.buffers.get(event.run_id);
    if (!buffer) {
      buffer = [];
      this.buffers.set(event.run_id, buffer);
    }
    
    buffer.push(event);
    
    // Evict oldest if over capacity
    if (buffer.length > this.maxSize) {
      buffer.shift();
    }
  }
  
  getFrom(seq: number): SSEEventEnvelope[] {
    // Find buffer by run_id from first event (all events in buffer have same run_id)
    for (const buffer of this.buffers.values()) {
      if (buffer.length > 0 && buffer[0].run_id) {
        return buffer.filter(e => e.seq >= seq);
      }
    }
    return [];
  }
  
  getAll(): SSEEventEnvelope[] {
    const all: SSEEventEnvelope[] = [];
    for (const buffer of this.buffers.values()) {
      all.push(...buffer);
    }
    return all;
  }
  
  clear(runId: string): void {
    this.buffers.delete(runId);
  }
  
  size(runId: string): number {
    return this.buffers.get(runId)?.length ?? 0;
  }
}
```

### 3.7 SSE HTTP Endpoint

```typescript
// src/api/routes/sse.ts

import type { FastifyInstance } from 'fastify';
import type { SSEStreamController } from '../../sse/stream.js';
import type { EventBuffer } from '../../sse/buffer.js';
import type { RunManager } from '../../orchestrator/run-manager.js';

export interface SSERouteOptions {
  streamController: SSEStreamController;
  eventBuffer: EventBuffer;
  runManager: RunManager;
  keepAliveIntervalMs?: number;
}

/**
 * Register SSE endpoint: GET /api/v0/runs/:runId/stream
 * 
 * Headers:
 *   - Accept: text/event-stream
 *   - Last-Event-ID: <seq> (optional, for replay from seq)
 * 
 * Query params:
 *   - replayFrom: <seq> (alternative to Last-Event-ID header)
 */
export async function sseRoutes(
  fastify: FastifyInstance,
  options: SSERouteOptions
): Promise<void> {
  const { streamController, eventBuffer, runManager, keepAliveIntervalMs = 30000 } = options;
  
  fastify.get('/api/v0/runs/:runId/stream', {
    schema: {
      params: {
        type: 'object',
        properties: {
          runId: { type: 'string', pattern: '^[A-Z0-9]{26}$' }  // ULID
        },
        required: ['runId']
      },
      querystring: {
        type: 'object',
        properties: {
          replayFrom: { type: 'number', minimum: 0 }
        }
      }
    }
  }, async (request, reply) => {
    const { runId } = request.params as { runId: string };
    const { replayFrom } = request.query as { replayFrom?: number };
    
    // Validate run exists
    const run = await runManager.get(runId);
    if (!run) {
      reply.code(404).send({ error: 'Run not found' });
      return;
    }
    
    // Get replay position from header or query
    const lastEventId = request.headers['last-event-id'];
    const startSeq = replayFrom ?? (lastEventId ? parseInt(lastEventId as string, 10) : null);
    
    // Set SSE headers
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no'  // Disable nginx buffering
    });
    
    // Create SSE stream wrapper
    const stream: SSEStream = {
      write(event) {
        const data = JSON.stringify(event);
        reply.raw.write(`id: ${event.seq}\n`);
        reply.raw.write(`event: ${event.type}\n`);
        reply.raw.write(`data: ${data}\n\n`);
      },
      close() {
        reply.raw.end();
      },
      isOpen() {
        return !reply.raw.writableEnded;
      },
      getClientInfo() {
        return {
          ip: request.ip,
          userAgent: request.headers['user-agent']
        };
      }
    };
    
    // Register stream
    const cleanup = streamController.register(runId, stream);
    
    // Replay buffered events if requested
    if (startSeq !== null && !isNaN(startSeq)) {
      const bufferedEvents = eventBuffer.getFrom(startSeq);
      for (const event of bufferedEvents) {
        stream.write(event);
      }
    }
    
    // Send initial connection event
    stream.write({
      type: 'stream_connected',
      run_id: runId,
      ts: new Date().toISOString(),
      seq: 0,  // Special seq for connection event
      payload: {
        run_state: run.state,
        replay_from: startSeq
      }
    } as SSEEventEnvelope);
    
    // Keep-alive timer
    const keepAliveTimer = setInterval(() => {
      if (stream.isOpen()) {
        reply.raw.write(':keepalive\n\n');
      } else {
        clearInterval(keepAliveTimer);
      }
    }, keepAliveIntervalMs);
    
    // Handle client disconnect
    request.raw.on('close', () => {
      clearInterval(keepAliveTimer);
      cleanup();
    });
    
    // Handle run completion - close stream when run reaches terminal state
    const checkRunState = setInterval(async () => {
      const currentRun = await runManager.get(runId);
      if (currentRun?.state === 'completed' || 
          currentRun?.state === 'failed' || 
          currentRun?.state === 'cancelled' ||
          currentRun?.state === 'timed_out') {
        clearInterval(checkRunState);
        clearInterval(keepAliveTimer);
        cleanup();
      }
    }, 1000);
    
    // Return a never-resolving promise to keep connection open
    return new Promise(() => {});
  });
}
```

---

## 4. Test Strategy

### 4.1 Unit Tests

| Module | Test Coverage | Test File |
|--------|--------------|-----------|
| Envelope factory | Seq monotonicity, timestamp format, type safety | `src/sse/envelope.test.ts` |
| Event mapper | All pi-agent-core event mappings, null handling | `src/sse/mapper.test.ts` |
| Stream controller | Register/broadcast/close, cleanup on disconnect | `src/sse/stream.test.ts` |
| Bounded buffer | FIFO eviction, getFrom seq, clear | `src/sse/buffer.test.ts` |
| SSE endpoint | Header validation, replay, keep-alive, run completion close | `src/api/routes/sse.test.ts` |

**Test Commands:**
```bash
# Run all SSE tests
npm test -- src/sse/

# Run with coverage
npm test -- --coverage src/sse/

# Watch mode
npm test -- --watch src/sse/
```

### 4.2 Integration Tests

| Scenario | Test File | Description |
|----------|-----------|-------------|
| End-to-end event streaming | `tests/integration/sse-streaming.test.ts` | Full run → events → SSE client |
| Client reconnect with replay | `tests/integration/sse-replay.test.ts` | Disconnect, reconnect from seq |
| Multiple concurrent clients | `tests/integration/sse-multiclient.test.ts` | Multiple clients for same run |
| Backpressure handling | `tests/integration/sse-backpressure.test.ts` | Slow consumer doesn't block |
| Run completion closes streams | `tests/integration/sse-completion.test.ts` | Terminal state → connection close |
| Event ordering guarantees | `tests/integration/sse-ordering.test.ts` | Seq monotonicity under load |

**Integration Test Commands:**
```bash
# Run SSE integration tests
npm run test:integration -- tests/integration/sse-*.test.ts

# Run with full orchestrator
npm run test:integration:e2e
```

### 4.3 Test Utilities

Create `src/test-utils/sse-helpers.ts`:

```typescript
/** Create a mock SSE stream for testing */
export function createMockStream(): MockSSEStream;

/** Collect events from a stream */
export async function collectEvents(stream: AsyncIterable<SSEEventEnvelope>): Promise<SSEEventEnvelope[]>;

/** Create a test client that connects to SSE endpoint */
export function createSSEClient(url: string, options?: SSEClientOptions): SSETestClient;

/** Wait for specific event type */
export function waitForEvent(events: SSEEventEnvelope[], type: SSEEventType, timeoutMs?: number): Promise<SSEEventEnvelope>;

/** Verify event sequence monotonicity */
export function assertMonotonicSeq(events: SSEEventEnvelope[]): void;
```

---

## 5. Dependencies on Other Sections

| Dependency | Section | Impact |
|------------|---------|--------|
| Run model states | Run Model + Scheduling | SSE emits orchestrator events (run_queued, run_started, etc.) |
| Run manager | Run Model + Scheduling | SSE endpoint queries run state, needs RunManager interface |
| Agent worker | Agent Integration | Worker produces pi-agent-core events that get mapped to SSE |
| HTTP server setup | Project Setup | SSE routes need to be registered with Fastify |

**Dependency Graph:**
```
SSE API (this section)
    ↓ depends on
Run Model + Scheduling (run states, run manager)
    ↓ depends on
Project Setup (HTTP server, dependencies)
    ↓ depends on
Agent Integration (pi-agent-core events)
```

**Key Integration Points:**
1. **Run Manager**: SSE endpoint validates run existence via `RunManager.get(runId)`
2. **Agent Worker**: Worker subscribes to pi-agent-core events and forwards to SSE broadcaster
3. **State Changes**: Orchestrator emits lifecycle events (run_queued → run_started → run_completed) via SSE

---

## 6. Reference Links

### Documentation
- [Proposal](../../openspec/changes/orchestrator-v0/proposal.md) - Change proposal with event-streaming capability
- [Design](../../openspec/changes/orchestrator-v0/design.md) - Design decisions on event streaming as thin adaptation
- [Event Streaming Spec](../../openspec/changes/orchestrator-v0/specs/event-streaming/spec.md) - Detailed SSE requirements
- [Architecture v0](../../architecture/agent-runtime-v0.md) - Component overview and event flow
- [Coding Standards](../../CODING_STANDARDS.md) - Code quality and dependency rules

### Research
- [pi-agent-core Events](../../research/pi-agent-core/events.md) - Event model reference (message_update, tool_execution_*)
- [pi-agent-core README](../../research/pi-agent-core/README.md) - SDK overview and event-driven architecture

### Related Plans
- [Run Model + Scheduling](./run-model-scheduling.md) - Run states and lifecycle events
- [Project Setup](./project-setup.md) - HTTP server and project structure

### Related Beans
- Parent: `minerva-5rrj` (orchestrator-v0 overall)
- This bean: `minerva-ha33` (SSE API)
- Siblings:
  - Run Model + Scheduling (`minerva-g1y9`) - **BLOCKING DEPENDENCY**
  - Agent Pack Loading
  - Daytona Sandbox Adapter
  - Tool Integration

---

## 7. Implementation Notes

### 7.1 Event Sequencing Strategy

- **Monotonic seq per run**: Each run has its own sequence counter starting at 1
- **Seq is not gapless**: Client should not expect consecutive seq numbers (some events may be filtered)
- **Seq for ordering only**: Use seq for ordering, not for counting events

### 7.2 Backpressure Strategy

- **Fast producer, slow consumer**: Events buffer in memory (bounded)
- **Consumer too slow**: Buffer evicts oldest events (configurable strategy for v1)
- **Client disconnect**: Stream is closed, buffer eventually cleared on run completion

### 7.3 Connection Lifecycle

```
Client connects
  → Validate run exists
  → Register stream
  → Replay buffered events (if requested)
  → Send stream_connected event
  → Start keep-alive timer
  
  [Events flow during run]
  
Run completes/cancels/fails/times_out
  → Check run state periodically
  → Close all streams for run
  → Cleanup timers and buffers
  
Client disconnects
  → Detect close event
  → Unregister stream
  → Cleanup (but keep buffer for reconnect)
```

### 7.4 Open Questions

1. **Replay window**: How many events to buffer? (default: 1000, configurable)
2. **Multi-instance**: Buffer is in-memory; Redis-backed buffer for multi-instance deployments (v1)
3. **Event versioning**: When to bump envelope version? (breaking changes only)
4. **Filtering**: Should clients be able to filter by event category? (v1 enhancement)
