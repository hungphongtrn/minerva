/**
 * Tool Events Mapper
 *
 * Maps pi-agent-core tool lifecycle events to SSE events.
 */

import type { SSEEventEnvelope } from './types.js';
import type { ToolEventEmitter } from '../tools/types.js';

/**
 * Creates a ToolEventEmitter that forwards events to an SSE broadcaster
 */
export function createToolEventEmitter(
  runId: string,
  broadcast: (event: SSEEventEnvelope) => void,
  sequencer: { next: (runId: string) => number }
): ToolEventEmitter {
  return {
    emitStart(toolCallId: string, toolName: string, args: Record<string, unknown>): void {
      const event: SSEEventEnvelope = {
        type: 'tool_execution_start',
        run_id: runId,
        ts: new Date().toISOString(),
        seq: sequencer.next(runId),
        payload: {
          tool_call_id: toolCallId,
          tool_name: toolName,
          args,
        },
      };
      broadcast(event);
    },

    emitUpdate(
      toolCallId: string,
      toolName: string,
      partialResult: { type: 'stdout' | 'stderr' | 'progress'; data: string }
    ): void {
      const event: SSEEventEnvelope = {
        type: 'tool_execution_update',
        run_id: runId,
        ts: new Date().toISOString(),
        seq: sequencer.next(runId),
        payload: {
          tool_call_id: toolCallId,
          tool_name: toolName,
          partial_result: partialResult,
        },
      };
      broadcast(event);
    },

    emitEnd(
      toolCallId: string,
      toolName: string,
      result: unknown,
      isError: boolean,
      durationMs: number
    ): void {
      const event: SSEEventEnvelope = {
        type: 'tool_execution_end',
        run_id: runId,
        ts: new Date().toISOString(),
        seq: sequencer.next(runId),
        payload: {
          tool_call_id: toolCallId,
          tool_name: toolName,
          result,
          is_error: isError,
          duration_ms: durationMs,
        },
      };
      broadcast(event);
    },
  };
}

/**
 * No-op event emitter for testing or when events are not needed
 */
export function createNoopToolEventEmitter(): ToolEventEmitter {
  return {
    emitStart: () => {},
    emitUpdate: () => {},
    emitEnd: () => {},
  };
}
