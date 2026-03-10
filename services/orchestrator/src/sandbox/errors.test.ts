import { describe, it, expect } from 'vitest';
import {
  SandboxError,
  WorkspaceNotFoundError,
  WorkspaceCreationError,
  PathTraversalError,
  FileTooLargeError,
  CommandTimeoutError,
  NetworkIsolationError,
} from './errors.js';

describe('SandboxError', () => {
  it('should create error with code and workspaceId', () => {
    const error = new SandboxError('Test error', 'TEST_CODE', 'ws-1');
    
    expect(error.message).toBe('Test error');
    expect(error.code).toBe('TEST_CODE');
    expect(error.workspaceId).toBe('ws-1');
    expect(error.name).toBe('SandboxError');
  });
});

describe('WorkspaceNotFoundError', () => {
  it('should create error with workspaceId', () => {
    const error = new WorkspaceNotFoundError('ws-123');
    
    expect(error.message).toBe('Workspace not found: ws-123');
    expect(error.code).toBe('WORKSPACE_NOT_FOUND');
    expect(error.workspaceId).toBe('ws-123');
    expect(error.name).toBe('WorkspaceNotFoundError');
  });
});

describe('WorkspaceCreationError', () => {
  it('should create error with message and userId', () => {
    const error = new WorkspaceCreationError('Failed to create', 'user-1');
    
    expect(error.message).toBe('Failed to create');
    expect(error.code).toBe('WORKSPACE_CREATION_FAILED');
    expect(error.workspaceId).toBe('user-1');
    expect(error.name).toBe('WorkspaceCreationError');
  });
});

describe('PathTraversalError', () => {
  it('should create error with path and reason', () => {
    const error = new PathTraversalError('../../../etc/passwd', 'Path escapes root', 'ws-1');
    
    expect(error.message).toBe('Path traversal detected: ../../../etc/passwd - Path escapes root');
    expect(error.code).toBe('PATH_TRAVERSAL_DETECTED');
    expect(error.attemptedPath).toBe('../../../etc/passwd');
    expect(error.reason).toBe('Path escapes root');
    expect(error.workspaceId).toBe('ws-1');
    expect(error.name).toBe('PathTraversalError');
  });
});

describe('FileTooLargeError', () => {
  it('should create error with path, size, and maxSize', () => {
    const error = new FileTooLargeError('large.bin', 15 * 1024 * 1024, 10 * 1024 * 1024, 'ws-1');
    
    expect(error.message).toBe('File too large: large.bin (15728640 bytes, max 10485760 bytes)');
    expect(error.code).toBe('FILE_TOO_LARGE');
    expect(error.path).toBe('large.bin');
    expect(error.size).toBe(15728640);
    expect(error.maxSize).toBe(10485760);
    expect(error.workspaceId).toBe('ws-1');
    expect(error.name).toBe('FileTooLargeError');
  });
});

describe('CommandTimeoutError', () => {
  it('should create error with command and timeout', () => {
    const error = new CommandTimeoutError('sleep 100', 5000, 'ws-1');
    
    expect(error.message).toBe('Command timed out after 5000ms: sleep 100');
    expect(error.code).toBe('COMMAND_TIMEOUT');
    expect(error.command).toBe('sleep 100');
    expect(error.timeoutMs).toBe(5000);
    expect(error.workspaceId).toBe('ws-1');
    expect(error.name).toBe('CommandTimeoutError');
  });
});

describe('NetworkIsolationError', () => {
  it('should create error with message and check results', () => {
    const checks = [
      { name: 'HTTP', passed: false, details: 'Connection succeeded' },
      { name: 'DNS', passed: true },
    ];
    const error = new NetworkIsolationError('Network not isolated', checks, 'ws-1');
    
    expect(error.message).toBe('Network not isolated');
    expect(error.code).toBe('NETWORK_ISOLATION_FAILED');
    expect(error.checkResults).toEqual(checks);
    expect(error.workspaceId).toBe('ws-1');
    expect(error.name).toBe('NetworkIsolationError');
  });
});
