import type {
  ExecutionChunk,
  NetworkCheckResult,
  Workspace,
  WorkspaceStrategy,
} from '../../src/sandbox/types.js';
import type { ISandboxAdapter } from '../../src/sandbox/adapter.js';

export class MockSandboxAdapter implements ISandboxAdapter {
  private readonly workspaces = new Map<string, Workspace>();
  private readonly files = new Map<string, string>();

  async getOrCreateWorkspace(userId: string, _strategy: WorkspaceStrategy): Promise<Workspace> {
    const workspaceId = `ws-${userId}`;
    const existing = this.workspaces.get(workspaceId);
    if (existing) {
      return existing;
    }

    const workspace: Workspace = {
      id: workspaceId,
      userId,
      createdAt: new Date(),
      lastUsedAt: new Date(),
      isReused: false,
      rootPath: '/workspace',
    };

    this.workspaces.set(workspaceId, workspace);
    return workspace;
  }

  async destroyWorkspace(workspaceId: string): Promise<void> {
    this.workspaces.delete(workspaceId);
  }

  async *execute(
    _workspaceId: string,
    command: string
  ): AsyncIterable<ExecutionChunk> {
    if (command.includes('slow')) {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }

    if (command.startsWith('echo ')) {
      yield {
        type: 'stdout',
        data: `${command.replace(/^echo\s+/, '').replace(/["']/g, '')}\n`,
        timestamp: Date.now(),
      };
    } else {
      yield {
        type: 'stdout',
        data: `executed:${command}\n`,
        timestamp: Date.now(),
      };
    }

    yield { type: 'exit', data: 0, timestamp: Date.now() };
  }

  async readFile(workspaceId: string, filePath: string): Promise<string> {
    return this.files.get(`${workspaceId}:${filePath}`) ?? '';
  }

  async writeFile(workspaceId: string, filePath: string, content: string): Promise<void> {
    this.files.set(`${workspaceId}:${filePath}`, content);
  }

  async validateNetworkIsolation(_workspaceId: string): Promise<NetworkCheckResult> {
    return {
      isIsolated: true,
      checks: [{ name: 'mock', passed: true, details: 'Mock isolation enabled' }],
    };
  }
}
