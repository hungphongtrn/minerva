export enum WorkspaceStrategy {
  PER_RUN = 'per_run',
  PER_USER = 'per_user',
}

export interface Workspace {
  id: string;
  userId: string;
  createdAt: Date;
  lastUsedAt: Date;
  isReused: boolean;
  rootPath: string;
}

export interface WorkspaceConfig {
  image: string;
  resources: {
    cpu: number;
    memory: string;
    disk: string;
  };
  network: {
    outbound: 'none' | 'restricted' | 'full';
  };
  timeout: {
    idleMinutes: number;
    maxLifetimeMinutes: number;
  };
}

export interface ExecutionOptions {
  timeoutMs?: number;
  workingDir?: string;
  env?: Record<string, string>;
  signal?: AbortSignal;
}

export interface ExecutionChunk {
  type: 'stdout' | 'stderr' | 'exit';
  data: string | number;
  timestamp: number;
}

export interface ExecutionResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export interface FileReadOptions {
  encoding?: BufferEncoding;
  maxSize?: number;
}

export interface FileWriteOptions {
  encoding?: BufferEncoding;
  createDirs?: boolean;
  mode?: number;
}

export interface PathValidationResult {
  isValid: boolean;
  normalizedPath: string;
  error?: string;
}

export interface NetworkCheckResult {
  isIsolated: boolean;
  checks: Array<{
    name: string;
    passed: boolean;
    details?: string;
  }>;
}
