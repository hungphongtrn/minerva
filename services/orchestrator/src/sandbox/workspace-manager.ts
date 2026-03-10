import type { DaytonaClient } from './daytona-client.js';
import type { Workspace, WorkspaceConfig, WorkspaceStrategy } from './types.js';
import {
  createProvisioningStrategy,
  type WorkspaceProvisioningStrategy,
} from './strategy.js';
import {
  WorkspaceNotFoundError,
  WorkspaceCreationError,
} from './errors.js';

export interface WorkspaceManagerConfig {
  strategy: WorkspaceStrategy;
  workspaceConfig: WorkspaceConfig;
}

export class WorkspaceManager {
  private strategy: WorkspaceProvisioningStrategy;
  private workspaces: Map<string, Workspace> = new Map();

  constructor(
    private client: DaytonaClient,
    private config: WorkspaceManagerConfig
  ) {
    this.strategy = createProvisioningStrategy(config.strategy);
  }

  async getOrCreateWorkspace(userId: string): Promise<{
    workspace: Workspace;
    isReused: boolean;
  }> {
    // Check if we should reuse an existing workspace
    const existing = await this.strategy.shouldReuse(userId);
    if (existing) {
      // Verify the workspace still exists
      const daytonaWorkspace = await this.client.getWorkspace(existing.id);
      if (daytonaWorkspace) {
        const workspace: Workspace = {
          ...existing,
          lastUsedAt: new Date(),
          isReused: true,
        };
        this.workspaces.set(workspace.id, workspace);
        this.strategy.markUsed(workspace);
        return { workspace, isReused: true };
      }
    }

    // Create a new workspace
    try {
      const daytonaWorkspace = await this.client.createWorkspace(
        userId,
        this.config.workspaceConfig
      );

      const workspace: Workspace = {
        id: daytonaWorkspace.id,
        userId,
        createdAt: new Date(),
        lastUsedAt: new Date(),
        isReused: false,
        rootPath: this.client.getWorkspaceRoot(),
      };

      this.workspaces.set(workspace.id, workspace);
      this.strategy.markUsed(workspace);

      return { workspace, isReused: false };
    } catch (error) {
      throw new WorkspaceCreationError(
        error instanceof Error ? error.message : 'Unknown error',
        userId
      );
    }
  }

  getWorkspace(workspaceId: string): Promise<Workspace> {
    const workspace = this.workspaces.get(workspaceId);
    if (!workspace) {
      return Promise.reject(new WorkspaceNotFoundError(workspaceId));
    }
    return Promise.resolve(workspace);
  }

  async destroyWorkspace(workspaceId: string): Promise<void> {
    const workspace = this.workspaces.get(workspaceId);
    if (!workspace) {
      throw new WorkspaceNotFoundError(workspaceId);
    }

    try {
      await this.client.destroyWorkspace(workspaceId);
      this.workspaces.delete(workspaceId);
      this.strategy.markDestroyed(workspaceId);
    } catch (error) {
      // Log but don't throw - workspace might already be destroyed
      console.error(`Failed to destroy workspace ${workspaceId}:`, error);
    }
  }

  async destroyAllWorkspaces(): Promise<void> {
    const promises = Array.from(this.workspaces.keys()).map((id) =>
      this.destroyWorkspace(id).catch((error) => {
        console.error(`Failed to destroy workspace ${id}:`, error);
      })
    );
    await Promise.all(promises);
  }
}
