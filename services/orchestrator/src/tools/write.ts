/**
 * Write Tool
 *
 * pi-agent-core tool definition for writing files with JSON Schema parameters.
 */

import { Type, type Static } from '@sinclair/typebox';
import type { ToolContext, ToolEventEmitter, ToolResult, AgentTool } from './types.js';
import {
  createSuccessResult,
  createErrorResult,
  mapErrorToToolError,
} from './types.js';

export const writeToolSchema = Type.Object({
  path: Type.String({
    description: 'Absolute or relative path to write the file',
  }),
  content: Type.String({
    description: 'Content to write',
  }),
  encoding: Type.Optional(
    Type.Union([Type.Literal('utf-8'), Type.Literal('base64')], {
      description: 'Content encoding',
      default: 'utf-8',
    })
  ),
  append: Type.Optional(
    Type.Boolean({
      description: 'Append to file instead of overwriting',
      default: false,
    })
  ),
});

export type WriteToolParams = Static<typeof writeToolSchema>;

export interface WriteToolResult {
  path: string;
  bytesWritten: number;
  encoding: string;
}

export function createWriteTool(
  writeFileFn: (
    workspaceId: string,
    path: string,
    content: string,
    options?: { encoding?: string; append?: boolean }
  ) => Promise<void>
): AgentTool<WriteToolResult> {
  return {
    name: 'write',
    label: 'Write File',
    description: 'Write content to a file in the sandbox workspace',
    parameters: writeToolSchema,
    execute: async (
      toolCallId: string,
      params: unknown,
      _signal: AbortSignal,
      eventEmitter: ToolEventEmitter,
      context?: ToolContext
    ): Promise<ToolResult<WriteToolResult>> => {
      const startTime = Date.now();

      // Validate context
      if (!context?.workspaceId) {
        const error = createErrorResult(
          'VALIDATION_ERROR',
          'No workspace context available'
        );
        eventEmitter.emitEnd(toolCallId, 'write', error, true, Date.now() - startTime);
        return error;
      }

      // Parse and validate parameters
      let parsed: WriteToolParams;
      try {
        parsed = params as WriteToolParams;
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
        eventEmitter.emitEnd(toolCallId, 'write', error, true, Date.now() - startTime);
        return error;
      }

      // Emit start event
      eventEmitter.emitStart(toolCallId, 'write', {
        path: parsed.path,
        encoding: parsed.encoding ?? 'utf-8',
        append: parsed.append ?? false,
      });

      try {
        // Execute file write
        await writeFileFn(context.workspaceId, parsed.path, parsed.content, {
          encoding: parsed.encoding ?? 'utf-8',
          append: parsed.append ?? false,
        });

        const result: WriteToolResult = {
          path: parsed.path,
          bytesWritten: parsed.content.length,
          encoding: parsed.encoding ?? 'utf-8',
        };

        const duration = Date.now() - startTime;
        eventEmitter.emitEnd(toolCallId, 'write', result, false, duration);

        return createSuccessResult(result);
      } catch (error) {
        const duration = Date.now() - startTime;
        const toolError = mapErrorToToolError(error);
        const result = createErrorResult(toolError.code, toolError.message, toolError.details);
        eventEmitter.emitEnd(toolCallId, 'write', result, true, duration);
        return result;
      }
    },
  };
}
