import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createWriteTool } from './write.js';
import { createNoopToolEventEmitter } from '../sse/tool-events.js';

describe('createWriteTool', () => {
  const mockWriteFileFn = vi.fn();
  const mockEventEmitter = createNoopToolEventEmitter();

  beforeEach(() => {
    mockWriteFileFn.mockClear();
  });

  it('should have correct metadata', () => {
    const tool = createWriteTool(mockWriteFileFn);

    expect(tool.name).toBe('write');
    expect(tool.label).toBe('Write File');
    expect(tool.description).toBe('Write content to a file in the sandbox workspace');
  });

  it('should write file and return success', async () => {
    const tool = createWriteTool(mockWriteFileFn);
    mockWriteFileFn.mockResolvedValue(undefined);

    const result = await tool.execute(
      'call-1',
      { path: 'test.txt', content: 'Hello World' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockWriteFileFn).toHaveBeenCalledWith(
      'ws-1',
      'test.txt',
      'Hello World',
      {
        encoding: 'utf-8',
        append: false,
      }
    );
    expect(result.success).toBe(true);
    expect(result.data?.path).toBe('test.txt');
    expect(result.data?.bytesWritten).toBe(11);
  });

  it('should return error when workspace context is missing', async () => {
    const tool = createWriteTool(mockWriteFileFn);

    const result = await tool.execute(
      'call-1',
      { path: 'test.txt', content: 'test' },
      new AbortController().signal,
      mockEventEmitter
      // No context
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('VALIDATION_ERROR');
    expect(result.error?.message).toBe('No workspace context available');
  });

  it('should handle empty content', async () => {
    const tool = createWriteTool(mockWriteFileFn);
    mockWriteFileFn.mockResolvedValue(undefined);

    const result = await tool.execute(
      'call-1',
      { path: 'empty.txt', content: '' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockWriteFileFn).toHaveBeenCalledWith('ws-1', 'empty.txt', '', {
      encoding: 'utf-8',
      append: false,
    });
    expect(result.success).toBe(true);
    expect(result.data?.bytesWritten).toBe(0);
  });

  it('should support append mode', async () => {
    const tool = createWriteTool(mockWriteFileFn);
    mockWriteFileFn.mockResolvedValue(undefined);

    const result = await tool.execute(
      'call-1',
      { path: 'log.txt', content: 'New line\n', append: true },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockWriteFileFn).toHaveBeenCalledWith('ws-1', 'log.txt', 'New line\n', {
      encoding: 'utf-8',
      append: true,
    });
    expect(result.success).toBe(true);
  });

  it('should support base64 encoding', async () => {
    const tool = createWriteTool(mockWriteFileFn);
    mockWriteFileFn.mockResolvedValue(undefined);

    const result = await tool.execute(
      'call-1',
      { path: 'binary.bin', content: 'SGVsbG8=', encoding: 'base64' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockWriteFileFn).toHaveBeenCalledWith('ws-1', 'binary.bin', 'SGVsbG8=', {
      encoding: 'base64',
      append: false,
    });
    expect(result.success).toBe(true);
    expect(result.data?.encoding).toBe('base64');
  });

  it('should handle permission denied error', async () => {
    const tool = createWriteTool(mockWriteFileFn);
    mockWriteFileFn.mockRejectedValue(new Error('EACCES: permission denied'));

    const result = await tool.execute(
      'call-1',
      { path: 'protected.txt', content: 'test' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('PERMISSION_DENIED');
  });
});
