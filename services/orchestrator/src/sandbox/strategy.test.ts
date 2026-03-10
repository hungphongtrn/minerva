import { describe, it, expect } from 'vitest';
import {
  PerRunStrategy,
  PerUserStrategy,
  createProvisioningStrategy,
} from './strategy.js';
import { WorkspaceStrategy, type Workspace } from './types.js';

const mockWorkspace = (id: string, userId: string): Workspace => ({
  id,
  userId,
  createdAt: new Date(),
  lastUsedAt: new Date(),
  isReused: false,
  rootPath: '/workspace',
});

describe('PerRunStrategy', () => {
  it('should never reuse workspaces', async () => {
    const strategy = new PerRunStrategy();
    
    const result = await strategy.shouldReuse('user-1');
    
    expect(result).toBeNull();
  });

  it('should do nothing when marking used', () => {
    const strategy = new PerRunStrategy();
    const workspace = mockWorkspace('ws-1', 'user-1');
    
    // Should not throw
    strategy.markUsed(workspace);
  });

  it('should do nothing when marking destroyed', () => {
    const strategy = new PerRunStrategy();
    
    // Should not throw
    strategy.markDestroyed('ws-1');
  });
});

describe('PerUserStrategy', () => {
  it('should return null when no workspace exists for user', async () => {
    const strategy = new PerUserStrategy();
    
    const result = await strategy.shouldReuse('user-1');
    
    expect(result).toBeNull();
  });

  it('should return workspace after marking used', async () => {
    const strategy = new PerUserStrategy();
    const workspace = mockWorkspace('ws-1', 'user-1');
    
    strategy.markUsed(workspace);
    const result = await strategy.shouldReuse('user-1');
    
    expect(result).toEqual(workspace);
  });

  it('should return null for different user', async () => {
    const strategy = new PerUserStrategy();
    const workspace = mockWorkspace('ws-1', 'user-1');
    
    strategy.markUsed(workspace);
    const result = await strategy.shouldReuse('user-2');
    
    expect(result).toBeNull();
  });

  it('should remove workspace when destroyed', async () => {
    const strategy = new PerUserStrategy();
    const workspace = mockWorkspace('ws-1', 'user-1');
    
    strategy.markUsed(workspace);
    strategy.markDestroyed('ws-1');
    const result = await strategy.shouldReuse('user-1');
    
    expect(result).toBeNull();
  });

  it('should only remove workspace with matching id', async () => {
    const strategy = new PerUserStrategy();
    const workspace1 = mockWorkspace('ws-1', 'user-1');
    const workspace2 = mockWorkspace('ws-2', 'user-2');
    
    strategy.markUsed(workspace1);
    strategy.markUsed(workspace2);
    strategy.markDestroyed('ws-1');
    
    const result1 = await strategy.shouldReuse('user-1');
    const result2 = await strategy.shouldReuse('user-2');
    
    expect(result1).toBeNull();
    expect(result2).toEqual(workspace2);
  });
});

describe('createProvisioningStrategy', () => {
  it('should create PerRunStrategy for PER_RUN', () => {
    const strategy = createProvisioningStrategy(WorkspaceStrategy.PER_RUN);
    
    expect(strategy).toBeInstanceOf(PerRunStrategy);
  });

  it('should create PerUserStrategy for PER_USER', () => {
    const strategy = createProvisioningStrategy(WorkspaceStrategy.PER_USER);
    
    expect(strategy).toBeInstanceOf(PerUserStrategy);
  });

  it('should throw for unknown strategy', () => {
    expect(() => createProvisioningStrategy('unknown' as WorkspaceStrategy)).toThrow(
      'Unknown workspace strategy: unknown'
    );
  });
});
