import type { Workspace } from './types.js';
import { WorkspaceStrategy } from './types.js';

export interface WorkspaceProvisioningStrategy {
  shouldReuse(userId: string): Promise<Workspace | null>;
  markUsed(workspace: Workspace): void;
  markDestroyed(workspaceId: string): void;
}

export class PerRunStrategy implements WorkspaceProvisioningStrategy {
  shouldReuse(_userId: string): Promise<null> {
    return Promise.resolve(null);
  }

  markUsed(_workspace: Workspace): void {
    // No-op - workspaces are not tracked for reuse
  }

  markDestroyed(_workspaceId: string): void {
    // No-op
  }
}

export class PerUserStrategy implements WorkspaceProvisioningStrategy {
  private workspaces: Map<string, Workspace> = new Map();

  shouldReuse(userId: string): Promise<Workspace | null> {
    const workspace = this.workspaces.get(userId);
    return Promise.resolve(workspace ?? null);
  }

  markUsed(workspace: Workspace): void {
    this.workspaces.set(workspace.userId, workspace);
  }

  markDestroyed(workspaceId: string): void {
    for (const [userId, workspace] of this.workspaces.entries()) {
      if (workspace.id === workspaceId) {
        this.workspaces.delete(userId);
        break;
      }
    }
  }
}

export function createProvisioningStrategy(
  strategy: WorkspaceStrategy
): WorkspaceProvisioningStrategy {
  switch (strategy) {
    case WorkspaceStrategy.PER_RUN:
      return new PerRunStrategy();
    case WorkspaceStrategy.PER_USER:
      return new PerUserStrategy();
    default:
      throw new Error(`Unknown workspace strategy: ${strategy as string}`);
  }
}
