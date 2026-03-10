/**
 * Tools Index
 *
 * Tool registry and factory for creating tools with injected Daytona adapter.
 */

import type { ISandboxAdapter } from '../sandbox/adapter.js';
import type { AgentTool } from './types.js';
import { createReadTool } from './read.js';
import { createWriteTool } from './write.js';
import { createBashTool } from './bash.js';

export type { AgentTool, ToolContext, ToolResult, ToolEventEmitter } from './types.js';
// Note: Tool creators are imported from individual tool files below

/**
 * Tool registry that holds all available tools
 */
export class ToolRegistry {
  private tools = new Map<string, AgentTool>();

  constructor(adapter: ISandboxAdapter) {
    // Initialize tools with injected adapter
    this.tools.set(
      'read',
      createReadTool(async (workspaceId, path, options) => {
        return adapter.readFile(workspaceId, path, {
          encoding: (options?.encoding as 'utf-8' | 'base64') ?? 'utf-8',
        });
      })
    );

    this.tools.set(
      'write',
      createWriteTool(async (workspaceId, path, content, options) => {
        await adapter.writeFile(workspaceId, path, content, {
          encoding: (options?.encoding as 'utf-8' | 'base64') ?? 'utf-8',
        });
      })
    );

    this.tools.set(
      'bash',
      createBashTool(async function* (workspaceId, command, options) {
        const chunks = adapter.execute(workspaceId, command, {
          timeoutMs: options?.timeoutMs,
          workingDir: options?.workingDir,
          env: options?.env,
        });

        for await (const chunk of chunks) {
          yield {
            type: chunk.type,
            data: chunk.data,
          };
        }
      })
    );
  }

  /**
   * Get a tool by name
   */
  getTool(name: string): AgentTool | undefined {
    return this.tools.get(name);
  }

  /**
   * Get all available tools
   */
  getAllTools(): AgentTool[] {
    return Array.from(this.tools.values());
  }

  /**
   * Get tool names
   */
  getToolNames(): string[] {
    return Array.from(this.tools.keys());
  }
}

/**
 * Factory function to create a tool registry
 */
export function createToolRegistry(adapter: ISandboxAdapter): ToolRegistry {
  return new ToolRegistry(adapter);
}

// Re-export tool schemas for external use
export { readToolSchema, type ReadToolParams, type ReadToolResult } from './read.js';
export { writeToolSchema, type WriteToolParams, type WriteToolResult } from './write.js';
export { bashToolSchema, type BashToolParams, type BashToolResult } from './bash.js';
export {
  createSuccessResult,
  createErrorResult,
  mapErrorToToolError,
  type ToolError,
  type ToolErrorCode,
} from './types.js';
