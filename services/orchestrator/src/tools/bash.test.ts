import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createBashTool, type ExecutionChunk } from './bash.js';
import { createNoopToolEventEmitter } from '../sse/tool-events.js';

function createChunkStream(chunks: ExecutionChunk[]): AsyncIterable<ExecutionChunk> {
  return {
    [Symbol.asyncIterator](): AsyncIterator<ExecutionChunk> {
      let index = 0;

      return {
        next(): Promise<IteratorResult<ExecutionChunk>> {
          if (index >= chunks.length) {
            return Promise.resolve({ done: true, value: undefined });
          }

          const value = chunks[index];
          index += 1;

          return Promise.resolve({ done: false, value });
        },
      };
    },
  };
}

function createFailingChunkStream(error: Error): AsyncIterable<ExecutionChunk> {
  return {
    [Symbol.asyncIterator](): AsyncIterator<ExecutionChunk> {
      return {
        next(): Promise<IteratorResult<ExecutionChunk>> {
          return Promise.reject(error);
        },
      };
    },
  };
}

describe('createBashTool', () => {
  const mockExecuteFn = vi.fn();
  const mockEventEmitter = createNoopToolEventEmitter();

  beforeEach(() => {
    mockExecuteFn.mockClear();
  });

  it('should have correct metadata', () => {
    const tool = createBashTool(mockExecuteFn);

    expect(tool.name).toBe('bash');
    expect(tool.label).toBe('Execute Command');
    expect(tool.description).toBe('Execute a bash command in the sandbox and stream output');
  });

  it('should execute command and return output', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() =>
      createChunkStream([
        { type: 'stdout', data: 'Hello World' },
        { type: 'exit', data: 0 },
      ])
    );

    const result = await tool.execute(
      'call-1',
      { command: 'echo "Hello World"' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(true);
    expect(result.data?.stdout).toBe('Hello World');
    expect(result.data?.exitCode).toBe(0);
  });

  it('should return error when workspace context is missing', async () => {
    const tool = createBashTool(mockExecuteFn);

    const result = await tool.execute(
      'call-1',
      { command: 'ls' },
      new AbortController().signal,
      mockEventEmitter
      // No context
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('VALIDATION_ERROR');
    expect(result.error?.message).toBe('No workspace context available');
  });

  it('should handle non-zero exit code as success (with exit code in result)', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() =>
      createChunkStream([
        { type: 'stdout', data: 'Error output' },
        { type: 'exit', data: 1 },
      ])
    );

    const result = await tool.execute(
      'call-1',
      { command: 'exit 1' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    // Per the plan: non-zero exit code is a "result" not an "error"
    expect(result.success).toBe(true);
    expect(result.data?.exitCode).toBe(1);
    expect(result.data?.stdout).toBe('Error output');
  });

  it('should emit streaming updates', async () => {
    const tool = createBashTool(mockExecuteFn);
    const emittedUpdates: Array<{ type: string; data: string }> = [];

    const capturingEmitter = {
      emitStart: () => {},
      emitUpdate: (
        _toolCallId: string,
        _toolName: string,
        partialResult: { type: 'stdout' | 'stderr' | 'progress'; data: string }
      ) => {
        emittedUpdates.push(partialResult);
      },
      emitEnd: () => {},
    };

    mockExecuteFn.mockImplementation(() =>
      createChunkStream([
        { type: 'stdout', data: 'Line 1\n' },
        { type: 'stdout', data: 'Line 2\n' },
        { type: 'exit', data: 0 },
      ])
    );

    await tool.execute(
      'call-1',
      { command: 'echo "test"' },
      new AbortController().signal,
      capturingEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(emittedUpdates).toHaveLength(2);
    expect(emittedUpdates[0]).toEqual({ type: 'stdout', data: 'Line 1\n' });
    expect(emittedUpdates[1]).toEqual({ type: 'stdout', data: 'Line 2\n' });
  });

  it('should respect timeout parameter', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() => createChunkStream([{ type: 'exit', data: 0 }]));

    await tool.execute(
      'call-1',
      { command: 'sleep 1', timeout: 30000 },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockExecuteFn).toHaveBeenCalledWith(
      'ws-1',
      'sleep 1',
      expect.objectContaining({ timeoutMs: 30000 })
    );
  });

  it('should handle abort signal', async () => {
    const tool = createBashTool(mockExecuteFn);
    const controller = new AbortController();

    mockExecuteFn.mockImplementation(() => {
      const chunks: ExecutionChunk[] = [{ type: 'stdout', data: 'output' }];
      controller.abort();
      chunks.push({ type: 'exit', data: 0 });
      return createChunkStream(chunks);
    });

    const result = await tool.execute(
      'call-1',
      { command: 'long-running' },
      controller.signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('CANCELLED');
    expect(result.error?.message).toBe('Command was cancelled');
  });

  it('should capture stderr output', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() =>
      createChunkStream([
        { type: 'stderr', data: 'Error message' },
        { type: 'exit', data: 0 },
      ])
    );

    const result = await tool.execute(
      'call-1',
      { command: 'cmd' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(true);
    expect(result.data?.stderr).toBe('Error message');
    expect(result.data?.stdout).toBe('');
  });

  it('should support working directory', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() => createChunkStream([{ type: 'exit', data: 0 }]));

    await tool.execute(
      'call-1',
      { command: 'pwd', cwd: '/tmp' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockExecuteFn).toHaveBeenCalledWith(
      'ws-1',
      'pwd',
      expect.objectContaining({ workingDir: '/tmp' })
    );
  });

  it('should support environment variables', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() => createChunkStream([{ type: 'exit', data: 0 }]));

    await tool.execute(
      'call-1',
      { command: 'echo $FOO', env: { FOO: 'bar' } },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockExecuteFn).toHaveBeenCalledWith(
      'ws-1',
      'echo $FOO',
      expect.objectContaining({ env: { FOO: 'bar' } })
    );
  });

  it('should handle timeout errors', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() =>
      createFailingChunkStream(new Error('Command execution ETIMEDOUT after 60000ms'))
    );

    const result = await tool.execute(
      'call-1',
      { command: 'sleep 100' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('TIMEOUT');
  });

  it('should track command duration', async () => {
    const tool = createBashTool(mockExecuteFn);

    mockExecuteFn.mockImplementation(() => createChunkStream([{ type: 'exit', data: 0 }]));

    const result = await tool.execute(
      'call-1',
      { command: 'ls' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(true);
    expect(result.data?.duration).toBeGreaterThanOrEqual(0);
  });
});
