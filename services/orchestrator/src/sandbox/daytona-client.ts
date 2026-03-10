import { Daytona, type Sandbox } from '@daytonaio/sdk';
import type { WorkspaceConfig } from './types.js';

export interface DaytonaClientConfig {
  serverUrl: string;
  apiKey: string;
  target: string;
}

export class DaytonaClient {
  private client: Daytona;

  constructor(config: DaytonaClientConfig) {
    this.client = new Daytona({
      apiUrl: config.serverUrl,
      apiKey: config.apiKey,
      target: config.target as 'us' | 'eu' | 'asia',
    });
  }

  async createWorkspace(
    userId: string,
    config: WorkspaceConfig
  ): Promise<Sandbox> {
    const sandbox = await this.client.create({
      language: 'typescript',
      envVars: {
        MINERVA_USER_ID: userId,
        MINERVA_WORKSPACE_MODE: 'ephemeral',
      },
      resources: {
        cpu: config.resources.cpu,
        memory: parseInt(config.resources.memory), // Convert '4Gi' to number
        disk: parseInt(config.resources.disk),
      },
    });

    return sandbox;
  }

  async getWorkspace(workspaceId: string): Promise<Sandbox | null> {
    try {
      const sandbox = await this.client.get(workspaceId);
      return sandbox;
    } catch {
      return null;
    }
  }

  async destroyWorkspace(workspaceId: string): Promise<void> {
    const sandbox = await this.getWorkspace(workspaceId);
    if (sandbox) {
      await this.client.remove(sandbox);
    }
  }

  async executeCommand(
    sandbox: Sandbox,
    command: string,
    options?: {
      timeout?: number;
      workingDir?: string;
      env?: Record<string, string>;
    }
  ): Promise<{
    exitCode: number;
    stdout: string;
    stderr: string;
  }> {
    const result = await sandbox.process.executeCommand(
      command,
      options?.workingDir || '/workspace',
      options?.timeout
    );

    return {
      exitCode: result.exitCode,
      stdout: result.artifacts?.stdout || '',
      stderr: '', // Daytona SDK returns combined output in stdout
    };
  }

  async readFile(sandbox: Sandbox, path: string): Promise<string> {
    const blob = await sandbox.fs.downloadFile(path);
    return await blob.text();
  }

  async writeFile(
    sandbox: Sandbox,
    path: string,
    content: string
  ): Promise<void> {
    const file = new File([content], path.split('/').pop() || 'file');
    await sandbox.fs.uploadFile(path, file);
  }

  getWorkspaceRoot(): string {
    return '/workspace';
  }
}
