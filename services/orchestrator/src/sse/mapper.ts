/**
 * SSE Event Mapper
 *
 * Maps pi-agent-core events and orchestrator events to SSE event envelopes.
 */

import type { SSEEventEnvelope, SSEEventType } from './types.js';
import type { EventSequencer } from './envelope.js';

/**
 * pi-agent-core Agent Event types
 * Based on research/pi-agent-core/events.md
 */
export interface AgentEvent {
  type: string;
  // Agent lifecycle
  messages?: unknown[];
  // Turn lifecycle
  turnNumber?: number;
  message?: unknown;
  toolResults?: unknown[];
  // Message lifecycle
  assistantMessageEvent?: {
    type: 'text_delta' | 'thinking_delta' | 'toolcall_start' | 'toolcall_delta';
    delta?: string;
    content?: unknown;
  };
  // Tool execution
  toolCallId?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  partialResult?: {
    type: 'stdout' | 'stderr' | 'progress';
    data: string;
  };
  result?: unknown;
  isError?: boolean;
  durationMs?: number;
}

export interface EventMapper {
  /** Map a pi-agent-core event to SSE envelope */
  map(agentEvent: AgentEvent, runId: string): SSEEventEnvelope | null;

  /** Map orchestrator lifecycle event */
  mapOrchestratorEvent(
    runId: string,
    type: Extract<
      SSEEventType,
      | 'run_queued'
      | 'run_started'
      | 'run_completed'
      | 'run_failed'
      | 'run_cancelled'
      | 'run_timed_out'
    >,
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
          payload: {},
        };

      case 'agent_end':
        return {
          type: 'agent_end',
          run_id: runId,
          ts,
          seq,
          payload: { messages: agentEvent.messages ?? [] },
        };

      case 'turn_start':
        return {
          type: 'turn_start',
          run_id: runId,
          ts,
          seq,
          payload: { turn_number: agentEvent.turnNumber ?? 0 },
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
            tool_results: agentEvent.toolResults ?? [],
          },
        };

      case 'message_start':
        return {
          type: 'message_start',
          run_id: runId,
          ts,
          seq,
          payload: { message: agentEvent.message },
        };

      case 'message_update':
        return {
          type: 'message_update',
          run_id: runId,
          ts,
          seq,
          payload: {
            message: agentEvent.message,
            delta_type: agentEvent.assistantMessageEvent?.type ?? 'text_delta',
            delta: agentEvent.assistantMessageEvent,
          },
        };

      case 'message_end':
        return {
          type: 'message_end',
          run_id: runId,
          ts,
          seq,
          payload: { message: agentEvent.message },
        };

      case 'tool_execution_start':
        return {
          type: 'tool_execution_start',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId ?? '',
            tool_name: agentEvent.toolName ?? '',
            args: agentEvent.args ?? {},
          },
        };

      case 'tool_execution_update':
        return {
          type: 'tool_execution_update',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId ?? '',
            tool_name: agentEvent.toolName ?? '',
            partial_result: agentEvent.partialResult ?? { type: 'stdout', data: '' },
          },
        };

      case 'tool_execution_end':
        return {
          type: 'tool_execution_end',
          run_id: runId,
          ts,
          seq,
          payload: {
            tool_call_id: agentEvent.toolCallId ?? '',
            tool_name: agentEvent.toolName ?? '',
            result: agentEvent.result,
            is_error: agentEvent.isError ?? false,
            duration_ms: agentEvent.durationMs ?? 0,
          },
        };

      default:
        // Unknown event type - log and skip
        console.warn(`Unknown agent event type: ${(agentEvent as { type: string }).type}`);
        return null;
    }
  }

  mapOrchestratorEvent(
    runId: string,
    type: Extract<
      SSEEventType,
      | 'run_queued'
      | 'run_started'
      | 'run_completed'
      | 'run_failed'
      | 'run_cancelled'
      | 'run_timed_out'
    >,
    payload: unknown
  ): SSEEventEnvelope {
    return {
      type,
      run_id: runId,
      ts: new Date().toISOString(),
      seq: this.sequencer.next(runId),
      payload,
    };
  }
}
