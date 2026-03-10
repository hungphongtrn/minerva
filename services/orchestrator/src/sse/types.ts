/**
 * SSE Types
 *
 * Type definitions for Server-Sent Events (SSE) API.
 * Includes event envelope, event types, and payload definitions.
 */

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
  // Stream connection
  | 'stream_connected'
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
  | 'orchestrator' // Orchestrator-level lifecycle
  | 'agent' // Agent loop events
  | 'turn' // Turn-level events
  | 'message' // Message streaming
  | 'tool'; // Tool execution

/** Map event type to category */
export function getEventCategory(type: SSEEventType): SSEEventCategory {
  if (type.startsWith('run_') || type === 'stream_connected') {
    return 'orchestrator';
  }
  if (type.startsWith('agent_')) {
    return 'agent';
  }
  if (type.startsWith('turn_')) {
    return 'turn';
  }
  if (type.startsWith('message_')) {
    return 'message';
  }
  if (type.startsWith('tool_execution_')) {
    return 'tool';
  }
  return 'orchestrator';
}

/** Base payload fields for all events */
interface BasePayload {
  // Reserved for future common fields
}

/** Orchestrator: Run queued */
export interface RunQueuedPayload extends BasePayload {
  queue_position: number;
  estimated_start?: string; // ISO timestamp
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

/** Stream connection event payload */
export interface StreamConnectedPayload extends BasePayload {
  run_state: string;
  replay_from?: number | null;
}

/** pi-agent-core: Agent lifecycle */
export interface AgentStartPayload extends BasePayload {
  // No additional fields
}

export interface AgentEndPayload extends BasePayload {
  messages: unknown[]; // AgentMessage[] serialized
}

/** pi-agent-core: Turn lifecycle */
export interface TurnStartPayload extends BasePayload {
  turn_number: number;
}

export interface TurnEndPayload extends BasePayload {
  turn_number: number;
  message: unknown; // AgentMessage serialized
  tool_results: unknown[];
}

/** pi-agent-core: Message lifecycle */
export interface MessageStartPayload extends BasePayload {
  message: unknown; // AgentMessage serialized
}

export interface MessageUpdatePayload extends BasePayload {
  message: unknown; // Partial AgentMessage
  delta_type: 'text_delta' | 'thinking_delta' | 'toolcall_start' | 'toolcall_delta';
  delta: unknown; // Type-specific delta
}

export interface MessageEndPayload extends BasePayload {
  message: unknown; // Final AgentMessage
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

/** Union type of all payload types */
export type SSEPayload =
  | RunQueuedPayload
  | RunStartedPayload
  | RunCompletedPayload
  | RunFailedPayload
  | RunCancelledPayload
  | RunTimedOutPayload
  | StreamConnectedPayload
  | AgentStartPayload
  | AgentEndPayload
  | TurnStartPayload
  | TurnEndPayload
  | MessageStartPayload
  | MessageUpdatePayload
  | MessageEndPayload
  | ToolExecutionStartPayload
  | ToolExecutionUpdatePayload
  | ToolExecutionEndPayload;
