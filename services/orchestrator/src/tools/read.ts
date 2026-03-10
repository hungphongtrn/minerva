/**
 * Read Tool
 *
 * pi-agent-core tool definition for reading files with JSON Schema parameters.
 */

import { Type, type Static } from '@sinclair/typebox';
import type { ToolContext, ToolEventEmitter, ToolResult, AgentTool } from './types.js';
import {
  createSuccessResult,
  createErrorResult,
  mapErrorToToolError,
} from './types.js';

export const readToolSchema = Type.Object({
  path: Type.String({
    description: 'Absolute or relative path to the file to read',
  }),
  encoding: Type.Optional(
    Type.Union(
      [Type.Literal('utf-8'), Type.Literal('base64'), Type.Literal('latin1')],
      {
        description: 'File encoding',
        default: 'utf-8',
      }
    )
  ),
  limit: Type.Optional(
    Type.Number({
      description: 'Maximum bytes to read (for large files)',
      minimum: 1,
      maximum: 1024 * 1024, // 1MB
      default: 1024 * 1024,
    })
  ),
});

export type ReadToolParams = Static<typeof readToolSchema>;

export interface ReadToolResult {
  content: string;
  size: number;
  encoding: string;
  truncated: boolean;
}

export function createReadTool(
  readFileFn: (
    workspaceId: string,
    path: string,
    options?: { encoding?: string; limit?: number }
  ) => Promise<string>
): AgentTool<ReadToolResult> {
  return {
    name: 'read',
    label: 'Read File',
    description: 'Read contents of a file in the sandbox workspace',
    parameters: readToolSchema,
    execute: async (
      toolCallId: string,
      params: unknown,
      _signal: AbortSignal,
      eventEmitter: ToolEventEmitter,
      context?: ToolContext
    ): Promise<ToolResult<ReadToolResult>> => {
      const startTime = Date.now();

      // Validate context
      if (!context?.workspaceId) {
        const error = createErrorResult(
          'VALIDATION_ERROR',
          'No workspace context available'
        );
        eventEmitter.emitEnd(toolCallId, 'read', error, true, Date.now() - startTime);
        return error;
      }

      // Parse and validate parameters
      let parsed: ReadToolParams;
      try {
        parsed = params as ReadToolParams;
        if (!parsed.path) {
          throw new Error('Path is required');
        }
      } catch (validationError) {
        const error = createErrorResult(
          'VALIDATION_ERROR',
          validationError instanceof Error
            ? validationError.message
            : 'Invalid parameters'
        );
        eventEmitter.emitEnd(toolCallId, 'read', error, true, Date.now() - startTime);
        return error;
      }

      // Emit start event
      eventEmitter.emitStart(toolCallId, 'read', {
        path: parsed.path,
        encoding: parsed.encoding ?? 'utf-8',
        limit: parsed.limit,
      });

      try {
        // Execute file read
        const content = await readFileFn(context.workspaceId, parsed.path, {
          encoding: parsed.encoding ?? 'utf-8',
          limit: parsed.limit,
        });

        const result: ReadToolResult = {
          content,
          size: content.length,
          encoding: parsed.encoding ?? 'utf-8',
          truncated: false, // TODO: Track if limit was applied
        };

        const duration = Date.now() - startTime;
        eventEmitter.emitEnd(toolCallId, 'read', result, false, duration);

        return createSuccessResult(result);
      } catch (error) {
        const duration = Date.now() - startTime;
        const toolError = mapErrorToToolError(error);
        const result = createErrorResult(toolError.code, toolError.message, toolError.details);
        eventEmitter.emitEnd(toolCallId, 'read', result, true, duration);
        return result;
      }
    },
  };
}
