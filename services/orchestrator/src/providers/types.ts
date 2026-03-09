export interface ILogger {
  debug(message: string, meta?: Record<string, unknown>): void;
  info(message: string, meta?: Record<string, unknown>): void;
  warn(message: string, meta?: Record<string, unknown>): void;
  error(message: string, error?: Error, meta?: Record<string, unknown>): void;
}

export interface WorkspaceConfig {
  name: string;
  image?: string;
  envVars?: Record<string, string>;
}

export interface Workspace {
  id: string;
  name: string;
  status: 'creating' | 'running' | 'stopped' | 'error';
  url?: string;
}

export interface CommandResult {
  exitCode: number;
  output: string;
  error?: string;
}

export interface IDaytonaClient {
  createWorkspace(config: WorkspaceConfig): Promise<Workspace>;
  getWorkspace(id: string): Promise<Workspace | null>;
  executeCommand(workspaceId: string, command: string): Promise<CommandResult>;
}