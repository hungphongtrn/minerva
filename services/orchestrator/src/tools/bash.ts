/**
 * Bash Tool
 *
 * pi-agent-core tool definition for executing bash commands with JSON Schema parameters.
 */

import { Type, type Static } from '@sinclair/typebox';
import type { ToolContext, ToolEventEmitter, ToolResult, AgentTool } from './types.js';
import {
  createSuccessResult,
  createErrorResult,
  mapErrorToToolError,
} from './types.js';

export const bashToolSchema = Type.Object({
  command: Type.String({
    description: 'Shell command to execute',
  }),
  cwd: Type.Optional(
    Type.String({
      description: 'Working directory for command execution',
    })
  ),
  timeout: Type.Optional(
    Type.Number({
      description: 'Timeout in milliseconds (max 300000 = 5min)',
      minimum: 1000,
      maximum: 300000,
      default: 60000,
    })
  ),
  env: Type.Optional(
    Type.Record(Type.String(), Type.String(), {
      description: 'Environment variables to set',
    })
  ),
});

export type BashToolParams = Static<typeof bashToolSchema>;

export interface BashToolResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  duration: number; // ms
  truncated: boolean; // if output exceeded max size
}

export interface ExecutionChunk {
  type: 'stdout' | 'stderr' | 'exit';
  data: string | number;
}

export function createBashTool(
  executeFn: (
    workspaceId: string,
    command: string,
    options?: { timeoutMs?: number; workingDir?: string; env?: Record<string, string> }
  ) => AsyncIterable<ExecutionChunk>
): AgentTool<BashToolResult> {
  return {
    name: 'bash',
    label: 'Execute Command',
    description: 'Execute a bash command in the sandbox and stream output',
    parameters: bashToolSchema,
    execute: async (
      toolCallId: string,
      params: unknown,
      signal: AbortSignal,
      eventEmitter: ToolEventEmitter,
      context?: ToolContext
    ): Promise<ToolResult<BashToolResult>> => {
      const startTime = Date.now();

      // Validate context
      if (!context?.workspaceId) {
        const error = createErrorResult(
          'VALIDATION_ERROR',
          'No workspace context available'
        );
        eventEmitter.emitEnd(toolCallId, 'bash', error, true, Date.now() - startTime);
        return error;
      }

      // Parse and validate parameters
      let parsed: BashToolParams;
      try {
        parsed = params as BashToolParams;
        if (!parsed.command) {
          throw new Error('Command is required');
        }
      } catch (validationError) {
        const error = createErrorResult(
          'VALIDATION_ERROR',
          validationError instanceof Error
            ? validationError.message
            : 'Invalid parameters'
        );
        eventEmitter.emitEnd(toolCallId, 'bash', error, true, Date.now() - startTime);
        return error;
      }

      // Emit start event
      eventEmitter.emitStart(toolCallId, 'bash', {
        command: parsed.command,
        cwd: parsed.cwd,
        timeout: parsed.timeout ?? 60000,
        env: parsed.env,
      });

      const stdoutChunks: string[] = [];
      const stderrChunks: string[] = [];
      let exitCode = 0;

      try {
        // Execute command with streaming
        for await (const chunk of executeFn(context.workspaceId, parsed.command, {
          timeoutMs: parsed.timeout ?? 60000,
          workingDir: parsed.cwd,
          env: parsed.env,
        })) {
          // Check for cancellation
          if (signal.aborted) {
            const duration = Date.now() - startTime;
            const error = createErrorResult('CANCELLED', 'Command was cancelled');
            eventEmitter.emitEnd(toolCallId, 'bash', error, true, duration);
            return error;
          }

          if (chunk.type === 'stdout') {
            const text = String(chunk.data);
            stdoutChunks.push(text);
            eventEmitter.emitUpdate(toolCallId, 'bash', {
              type: 'stdout',
              data: text,
            });
          } else if (chunk.type === 'stderr') {
            const text = String(chunk.data);
            stderrChunks.push(text);
            eventEmitter.emitUpdate(toolCallId, 'bash', {
              type: 'stderr',
              data: text,
            });
          } else if (chunk.type === 'exit') {
            exitCode = Number(chunk.data);
          }
        }

        const result: BashToolResult = {
          stdout: stdoutChunks.join(''),
          stderr: stderrChunks.join(''),
          exitCode,
          duration: Date.now() - startTime,
          truncated: false, // TODO: Track if output was truncated
        };

        const duration = Date.now() - startTime;
        const isError = exitCode !== 0;

        // Note: Non-zero exit code is a "result" not an "error" per plan requirements
        // Only actual execution failures (timeouts, cancellations, etc.) are errors
        eventEmitter.emitEnd(toolCallId, 'bash', result, isError, duration);

        return createSuccessResult(result);
      } catch (error) {
        const duration = Date.now() - startTime;
        const toolError = mapErrorToToolError(error);
        const result = createErrorResult(toolError.code, toolError.message, toolError.details);
        eventEmitter.emitEnd(toolCallId, 'bash', result, true, duration);
        return result;
      }
    },
  };
}
