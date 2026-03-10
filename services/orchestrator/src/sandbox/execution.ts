import type { Sandbox } from '@daytonaio/sdk';
import type { ExecutionOptions, ExecutionChunk } from './types.js';
import { CommandTimeoutError } from './errors.js';

export class ExecutionService {
  /**
   * Execute a command and stream output chunks
   */
  async *executeStreaming(
    sandbox: Sandbox,
    command: string,
    options?: ExecutionOptions
  ): AsyncGenerator<ExecutionChunk> {
    const timeoutMs = options?.timeoutMs || 300000; // 5 minutes default

    // Create a session for this execution
    const sessionId = `exec-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    
    try {
      await sandbox.process.createSession(sessionId);

      // Execute the command in the session
      const result = await sandbox.process.executeSessionCommand(
        sessionId,
        {
          command,
          async: false,
        },
        Math.floor(timeoutMs / 1000)
      );

      // For now, we simulate streaming by returning the full output
      // In a future version, this could use the session command logs API
      if (result.output) {
        yield {
          type: 'stdout',
          data: result.output,
          timestamp: Date.now(),
        };
      }

      yield {
        type: 'exit',
        data: result.exitCode ?? 0,
        timestamp: Date.now(),
      };

    } catch (error) {
      if (error instanceof Error && error.message.includes('timeout')) {
        throw new CommandTimeoutError(command, timeoutMs, sandbox.id);
      }
      
      yield {
        type: 'stderr',
        data: error instanceof Error ? error.message : 'Unknown error',
        timestamp: Date.now(),
      };
      
      yield {
        type: 'exit',
        data: 1,
        timestamp: Date.now(),
      };
    } finally {
      // Clean up session
      try {
        await sandbox.process.deleteSession(sessionId);
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  /**
   * Execute a command and return the complete result
   */
  async execute(
    sandbox: Sandbox,
    command: string,
    options?: ExecutionOptions
  ): Promise<{
    exitCode: number;
    stdout: string;
    stderr: string;
    durationMs: number;
  }> {
    const startTime = Date.now();
    const chunks: string[] = [];
    let exitCode = 0;

    for await (const chunk of this.executeStreaming(sandbox, command, options)) {
      if (chunk.type === 'stdout' || chunk.type === 'stderr') {
        chunks.push(String(chunk.data));
      } else if (chunk.type === 'exit') {
        exitCode = Number(chunk.data);
      }
    }

    const stdout = chunks.join('');
    const durationMs = Date.now() - startTime;

    return {
      exitCode,
      stdout,
      stderr: '', // Combined in stdout by Daytona SDK
      durationMs,
    };
  }
}
