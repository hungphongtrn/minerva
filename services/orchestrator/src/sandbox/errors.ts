export class SandboxError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly workspaceId?: string
  ) {
    super(message);
    this.name = 'SandboxError';
  }
}

export class WorkspaceNotFoundError extends SandboxError {
  constructor(workspaceId: string) {
    super(`Workspace not found: ${workspaceId}`, 'WORKSPACE_NOT_FOUND', workspaceId);
    this.name = 'WorkspaceNotFoundError';
  }
}

export class WorkspaceCreationError extends SandboxError {
  constructor(message: string, userId?: string) {
    super(message, 'WORKSPACE_CREATION_FAILED', userId);
    this.name = 'WorkspaceCreationError';
  }
}

export class PathTraversalError extends SandboxError {
  constructor(
    public readonly attemptedPath: string,
    public readonly reason: string,
    workspaceId: string
  ) {
    super(
      `Path traversal detected: ${attemptedPath} - ${reason}`,
      'PATH_TRAVERSAL_DETECTED',
      workspaceId
    );
    this.name = 'PathTraversalError';
  }
}

export class FileTooLargeError extends SandboxError {
  constructor(
    public readonly path: string,
    public readonly size: number,
    public readonly maxSize: number,
    workspaceId: string
  ) {
    super(
      `File too large: ${path} (${size} bytes, max ${maxSize} bytes)`,
      'FILE_TOO_LARGE',
      workspaceId
    );
    this.name = 'FileTooLargeError';
  }
}

export class CommandExecutionError extends SandboxError {
  constructor(
    message: string,
    public readonly exitCode: number,
    public readonly stdout: string,
    public readonly stderr: string,
    workspaceId: string
  ) {
    super(message, 'COMMAND_EXECUTION_FAILED', workspaceId);
    this.name = 'CommandExecutionError';
  }
}

export class CommandTimeoutError extends SandboxError {
  constructor(
    public readonly command: string,
    public readonly timeoutMs: number,
    workspaceId: string
  ) {
    super(
      `Command timed out after ${timeoutMs}ms: ${command}`,
      'COMMAND_TIMEOUT',
      workspaceId
    );
    this.name = 'CommandTimeoutError';
  }
}

export class NetworkIsolationError extends SandboxError {
  constructor(
    message: string,
    public readonly checkResults: Array<{ name: string; passed: boolean; details?: string }>,
    workspaceId: string
  ) {
    super(message, 'NETWORK_ISOLATION_FAILED', workspaceId);
    this.name = 'NetworkIsolationError';
  }
}
