/**
 * SSE Module - Server-Sent Events for Run Streaming
 *
 * Provides real-time event streaming from agent runs to clients.
 */

// Types
export type {
  SSEEventEnvelope,
  SSEEventType,
  SSEEventCategory,
  SSEPayload,
  RunQueuedPayload,
  RunStartedPayload,
  RunCompletedPayload,
  RunFailedPayload,
  RunCancelledPayload,
  RunTimedOutPayload,
  StreamConnectedPayload,
  AgentStartPayload,
  AgentEndPayload,
  TurnStartPayload,
  TurnEndPayload,
  MessageStartPayload,
  MessageUpdatePayload,
  MessageEndPayload,
  ToolExecutionStartPayload,
  ToolExecutionUpdatePayload,
  ToolExecutionEndPayload,
} from './types.js';

// Envelope and Sequencer
export {
  MemoryEventSequencer,
  DefaultEnvelopeFactory,
  type EventSequencer,
  type EnvelopeFactory,
} from './envelope.js';

// Event Mapper
export {
  DefaultEventMapper,
  type EventMapper,
  type AgentEvent,
} from './mapper.js';

// Stream Controller
export {
  MemorySSEStreamController,
  type SSEStream,
  type SSEStreamController,
} from './stream.js';

// Event Buffer
export {
  BoundedEventBuffer,
  type EventBuffer,
} from './buffer.js';

// NestJS Module and Service
export { SSEModule } from './sse.module.js';
export { SSEService } from './sse.service.js';
export { SSEController } from './sse.controller.js';

// Tool Events
export {
  createToolEventEmitter,
  createNoopToolEventEmitter,
} from './tool-events.js';
