import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createReadTool } from './read.js';
import { createNoopToolEventEmitter } from '../sse/tool-events.js';

describe('createReadTool', () => {
  const mockReadFileFn = vi.fn();
  const mockEventEmitter = createNoopToolEventEmitter();

  beforeEach(() => {
    mockReadFileFn.mockClear();
  });

  it('should have correct metadata', () => {
    const tool = createReadTool(mockReadFileFn);

    expect(tool.name).toBe('read');
    expect(tool.label).toBe('Read File');
    expect(tool.description).toBe('Read contents of a file in the sandbox workspace');
  });

  it('should read file and return content', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockResolvedValue('File contents here');

    const result = await tool.execute(
      'call-1',
      { path: 'test.txt' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockReadFileFn).toHaveBeenCalledWith('ws-1', 'test.txt', {
      encoding: 'utf-8',
      limit: undefined,
    });
    expect(result.success).toBe(true);
    expect(result.data?.content).toBe('File contents here');
    expect(result.data?.size).toBe(18);
  });

  it('should return error when workspace context is missing', async () => {
    const tool = createReadTool(mockReadFileFn);

    const result = await tool.execute(
      'call-1',
      { path: 'test.txt' },
      new AbortController().signal,
      mockEventEmitter
      // No context
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('VALIDATION_ERROR');
    expect(result.error?.message).toBe('No workspace context available');
  });

  it('should handle empty file', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockResolvedValue('');

    const result = await tool.execute(
      'call-1',
      { path: 'empty.txt' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(true);
    expect(result.data?.content).toBe('');
    expect(result.data?.size).toBe(0);
  });

  it('should handle file not found error', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockRejectedValue(new Error('ENOENT: file not found'));

    const result = await tool.execute(
      'call-1',
      { path: 'missing.txt' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('FILE_NOT_FOUND');
  });

  it('should handle permission denied error', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockRejectedValue(new Error('EACCES: permission denied'));

    const result = await tool.execute(
      'call-1',
      { path: 'protected.txt' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(result.success).toBe(false);
    expect(result.error?.code).toBe('PERMISSION_DENIED');
  });

  it('should support custom encoding', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockResolvedValue('base64content');

    const result = await tool.execute(
      'call-1',
      { path: 'binary.bin', encoding: 'base64' },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockReadFileFn).toHaveBeenCalledWith('ws-1', 'binary.bin', {
      encoding: 'base64',
      limit: undefined,
    });
    expect(result.success).toBe(true);
    expect(result.data?.encoding).toBe('base64');
  });

  it('should support read limit', async () => {
    const tool = createReadTool(mockReadFileFn);
    mockReadFileFn.mockResolvedValue('partial content');

    const result = await tool.execute(
      'call-1',
      { path: 'large.txt', limit: 1024 },
      new AbortController().signal,
      mockEventEmitter,
      { workspaceId: 'ws-1', runId: 'run-1', userId: 'user-1' }
    );

    expect(mockReadFileFn).toHaveBeenCalledWith('ws-1', 'large.txt', {
      encoding: 'utf-8',
      limit: 1024,
    });
    expect(result.success).toBe(true);
  });
});
