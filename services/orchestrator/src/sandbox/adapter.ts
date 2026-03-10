import type { Sandbox } from '@daytonaio/sdk';
import type { DaytonaClient } from './daytona-client.js';
import type { WorkspaceManager } from './workspace-manager.js';
import type { ExecutionService } from './execution.js';
import type { FilesystemService } from './filesystem.js';
import type { NetworkValidationService } from './network.js';
import type {
  Workspace,
  WorkspaceStrategy,
  ExecutionOptions,
  ExecutionChunk,
  FileReadOptions,
  FileWriteOptions,
  NetworkCheckResult,
} from './types.js';
import { WorkspaceNotFoundError } from './errors.js';

export interface ISandboxAdapter {
  // Workspace lifecycle
  getOrCreateWorkspace(
    userId: string,
    strategy: WorkspaceStrategy
  ): Promise<Workspace>;
  destroyWorkspace(workspaceId: string): Promise<void>;

  // Execution
  execute(
    workspaceId: string,
    command: string,
    options?: ExecutionOptions
  ): AsyncIterable<ExecutionChunk>;

  // Filesystem
  readFile(workspaceId: string, path: string, options?: FileReadOptions): Promise<string>;
  writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options?: FileWriteOptions
  ): Promise<void>;

  // Validation
  validateNetworkIsolation(workspaceId: string): Promise<NetworkCheckResult>;
}

export class DaytonaSandboxAdapter implements ISandboxAdapter {
  private sandboxes: Map<string, Sandbox> = new Map();

  constructor(
    private client: DaytonaClient,
    private workspaceManager: WorkspaceManager,
    private executionService: ExecutionService,
    private filesystemService: FilesystemService,
    private networkService: NetworkValidationService
  ) {}

  async getOrCreateWorkspace(
    userId: string,
    _strategy: WorkspaceStrategy
  ): Promise<Workspace> {
    const { workspace } = await this.workspaceManager.getOrCreateWorkspace(userId);
    
    // Cache the Daytona sandbox reference
    const sandbox = await this.client.getWorkspace(workspace.id);
    if (sandbox) {
      this.sandboxes.set(workspace.id, sandbox);
    }
    
    return workspace;
  }

  async destroyWorkspace(workspaceId: string): Promise<void> {
    await this.workspaceManager.destroyWorkspace(workspaceId);
    this.sandboxes.delete(workspaceId);
  }

  async *execute(
    workspaceId: string,
    command: string,
    options?: ExecutionOptions
  ): AsyncIterable<ExecutionChunk> {
    const sandbox = await this.getSandbox(workspaceId);
    yield* this.executionService.executeStreaming(sandbox, command, options);
  }

  async readFile(
    workspaceId: string,
    path: string,
    options?: FileReadOptions
  ): Promise<string> {
    const sandbox = await this.getSandbox(workspaceId);
    return this.filesystemService.readFile(sandbox, path, options);
  }

  async writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options?: FileWriteOptions
  ): Promise<void> {
    const sandbox = await this.getSandbox(workspaceId);
    return this.filesystemService.writeFile(sandbox, path, content, options);
  }

  async validateNetworkIsolation(
    workspaceId: string
  ): Promise<NetworkCheckResult> {
    const sandbox = await this.getSandbox(workspaceId);
    return this.networkService.validateNetworkIsolation(sandbox);
  }

  private async getSandbox(workspaceId: string): Promise<Sandbox> {
    // Check cache first
    let sandbox = this.sandboxes.get(workspaceId);
    if (sandbox) {
      return sandbox;
    }

    // Fetch from Daytona
    const fetched = await this.client.getWorkspace(workspaceId);
    if (!fetched) {
      throw new WorkspaceNotFoundError(workspaceId);
    }
    sandbox = fetched;

    this.sandboxes.set(workspaceId, sandbox);
    return sandbox;
  }
}
