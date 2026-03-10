/**
 * Tool Types
 *
 * Shared type definitions for pi-agent-core tools with JSON Schema support.
 * Aligned with pi-agent-core tool contract and SSE event streaming.
 */

import type { TSchema } from '@sinclair/typebox';

/**
 * Tool error codes for deterministic error handling
 */
export type ToolErrorCode =
  | 'FILE_NOT_FOUND'
  | 'PERMISSION_DENIED'
  | 'COMMAND_FAILED'
  | 'VALIDATION_ERROR'
  | 'TIMEOUT'
  | 'CANCELLED'
  | 'UNKNOWN_ERROR';

/**
 * Structured error for deterministic error handling
 */
export interface ToolError {
  code: ToolErrorCode;
  message: string;
  details?: Record<string, unknown>;
}

/**
 * Tool result wrapper for consistent return types
 */
export interface ToolResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: ToolError;
}

/**
 * Tool execution context passed to all tools
 */
export interface ToolContext {
  workspaceId: string;
  runId: string;
  userId: string;
}

/**
 * Event emitter for tool lifecycle events
 */
export interface ToolEventEmitter {
  emitStart(toolCallId: string, toolName: string, args: Record<string, unknown>): void;
  emitUpdate(
    toolCallId: string,
    toolName: string,
    partialResult: { type: 'stdout' | 'stderr' | 'progress'; data: string }
  ): void;
  emitEnd(
    toolCallId: string,
    toolName: string,
    result: unknown,
    isError: boolean,
    durationMs: number
  ): void;
}

/**
 * pi-agent-core compatible tool definition
 */
export interface AgentTool<TResult = unknown> {
  name: string;
  label: string;
  description: string;
  parameters: TSchema;
  execute: (
    toolCallId: string,
    params: unknown,
    signal: AbortSignal,
    eventEmitter: ToolEventEmitter,
    context?: ToolContext
  ) => Promise<ToolResult<TResult>>;
}

/**
 * Tool registry for creating tools with injected dependencies
 */
export interface ToolRegistry {
  getTool(name: string): AgentTool | undefined;
  getAllTools(): AgentTool[];
}

/**
 * Helper to create structured success result
 */
export function createSuccessResult<T>(data: T): ToolResult<T> {
  return {
    success: true,
    data,
  };
}

/**
 * Helper to create structured error result
 */
export function createErrorResult(
  code: ToolErrorCode,
  message: string,
  details?: Record<string, unknown>
): ToolResult<never> {
  return {
    success: false,
    error: {
      code,
      message,
      details,
    },
  };
}

/**
 * Map unknown errors to structured ToolError
 */
export function mapErrorToToolError(error: unknown): ToolError {
  if (error && typeof error === 'object' && 'code' in error) {
    const err = error as ToolError;
    if (
      err.code === 'FILE_NOT_FOUND' ||
      err.code === 'PERMISSION_DENIED' ||
      err.code === 'COMMAND_FAILED' ||
      err.code === 'VALIDATION_ERROR' ||
      err.code === 'TIMEOUT' ||
      err.code === 'CANCELLED'
    ) {
      return err;
    }
  }

  // Map common error patterns
  const errorMessage = error instanceof Error ? error.message : String(error);

  if (errorMessage.includes('not found') || errorMessage.includes('ENOENT')) {
    return {
      code: 'FILE_NOT_FOUND',
      message: errorMessage,
    };
  }

  if (errorMessage.includes('permission') || errorMessage.includes('EACCES')) {
    return {
      code: 'PERMISSION_DENIED',
      message: errorMessage,
    };
  }

  if (errorMessage.includes('timeout') || errorMessage.includes('ETIMEDOUT')) {
    return {
      code: 'TIMEOUT',
      message: errorMessage,
    };
  }

  if (errorMessage.includes('cancelled') || errorMessage.includes('abort')) {
    return {
      code: 'CANCELLED',
      message: errorMessage,
    };
  }

  return {
    code: 'UNKNOWN_ERROR',
    message: errorMessage,
  };
}
