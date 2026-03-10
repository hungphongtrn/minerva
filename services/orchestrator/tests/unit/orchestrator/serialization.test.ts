/**
 * Serialization Tests
 *
 * Tests for single active run per user invariant.
 * Verifies that queue and lease work together to enforce serialization.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  RunManager,
  InMemoryRunRepository,
  InMemoryRunQueue,
  InMemoryLeaseManager,
  InMemoryCancellationRegistry,
  InMemoryTimeoutManager,
} from '@/services/index.js';
import { RunState } from '@/types/run.js';

describe('Single Active Run Per User Invariant', () => {
  let manager: RunManager;
  let repo: InMemoryRunRepository;
  let queue: InMemoryRunQueue;
  let leaseManager: InMemoryLeaseManager;
  let cancellationRegistry: InMemoryCancellationRegistry;
  let timeoutManager: InMemoryTimeoutManager;

  beforeEach(() => {
    repo = new InMemoryRunRepository();
    queue = new InMemoryRunQueue();
    leaseManager = new InMemoryLeaseManager();
    cancellationRegistry = new InMemoryCancellationRegistry();
    timeoutManager = new InMemoryTimeoutManager();

    manager = new RunManager(
      repo,
      queue,
      leaseManager,
      cancellationRegistry,
      timeoutManager,
      { defaultTimeoutMs: 10000, leaseTtlMs: 30000, maxTimeoutMs: 3600000 }
    );
  });

  describe('concurrent runs for different users', () => {
    it('should allow concurrent runs for different users', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });
      
      const run2 = await manager.createRun({
        userId: 'user-2',
        agentPackId: 'pack-1',
        prompt: 'World',
      });

      // Both should be able to acquire lease
      const acquired1 = await manager.acquireNextRun('user-1');
      const acquired2 = await manager.acquireNextRun('user-2');

      expect(acquired1).not.toBeNull();
      expect(acquired2).not.toBeNull();
      expect(acquired1!.id).toBe(run1.id);
      expect(acquired2!.id).toBe(run2.id);
    });

    it('should allow both users to start runs simultaneously', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });
      
      const run2 = await manager.createRun({
        userId: 'user-2',
        agentPackId: 'pack-1',
        prompt: 'World',
      });

      await manager.acquireNextRun('user-1');
      await manager.acquireNextRun('user-2');
      
      const started1 = await manager.startRun(run1.id);
      const started2 = await manager.startRun(run2.id);

      expect(started1.state).toBe(RunState.RUNNING);
      expect(started2.state).toBe(RunState.RUNNING);
    });
  });

  describe('serialization for same user', () => {
    it('should queue second run when first is active', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'First',
      });
      
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Second',
      });

      // First run acquires lease
      await manager.acquireNextRun('user-1');
      
      // Second run should be queued
      expect(run1.queuePosition).toBe(0);
      const position2 = await queue.getPosition(run2.id);
      expect(position2).toBe(0); // In queue, position 0
      
      // Try to acquire for same user should fail
      const secondAcquisition = await manager.acquireNextRun('user-1');
      expect(secondAcquisition).toBeNull();
    });

    it('should maintain FIFO order for queued runs', async () => {
      const runs: string[] = [];
      
      for (let i = 0; i < 5; i++) {
        const run = await manager.createRun({
          userId: 'user-1',
          agentPackId: 'pack-1',
          prompt: `Run ${i}`,
        });
        runs.push(run.id);
      }

      // Acquire first run
      await manager.acquireNextRun('user-1');
      
      // Remaining runs should be in FIFO order
      const queueLength = await queue.getLength('user-1');
      expect(queueLength).toBe(4);
      
      // Complete first run to allow next
      await manager.startRun(runs[0]);
      await manager.completeRun(runs[0]);
      
      // Now second run can be acquired
      const nextRun = await manager.acquireNextRun('user-1');
      expect(nextRun).not.toBeNull();
      expect(nextRun!.id).toBe(runs[1]);
    });
  });

  describe('active run blocks new leases', () => {
    it('should block new run while one is running', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Running',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);

      // Try to create and acquire another run
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Waiting',
      });

      // Should not be able to acquire while first is running
      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).toBeNull();
      
      // run2 should remain in queue
      const position = await queue.getPosition(run2.id);
      expect(position).not.toBeNull();
    });

    it('should block new acquisition while lease is active', async () => {
      // Create and acquire first run
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'First',
      });

      // Acquire run1
      await manager.acquireNextRun('user-1');
      
      // Create second run
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Second',
      });
      
      // Verify run2 is in queue
      const position = await queue.getPosition(run2.id);
      expect(position).toBe(0);
      
      // Try to acquire while run1 has active lease - should fail
      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).toBeNull();
      
      // Complete run1 to release lease
      await manager.startRun(run1.id);
      await manager.completeRun(run1.id);
      
      // Now should be able to acquire run2
      const acquired2 = await manager.acquireNextRun('user-1');
      expect(acquired2).not.toBeNull();
      expect(acquired2!.id).toBe(run2.id);
    });
  });

  describe('completed run allows new lease', () => {
    it('should allow new run after completion', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'First',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);
      await manager.completeRun(run1.id);

      // Verify lease is released
      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);

      // Should be able to create and start new run
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Second',
      });

      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).not.toBeNull();
      expect(acquired!.id).toBe(run2.id);
    });

    it('should update queue after completion', async () => {
      // Create multiple runs
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'First',
      });
      
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Second',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);
      await manager.completeRun(run1.id);

      // run2 should now be acquirable
      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired!.id).toBe(run2.id);
    });
  });

  describe('cancelled run releases lease', () => {
    it('should release lease on cancellation', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Cancellable',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);
      await manager.cancelRun(run1.id);

      // Verify lease is released
      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);

      // Should be able to start new run
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Next',
      });

      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).not.toBeNull();
    });

    it('should remove cancelled run from queue', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Will cancel',
      });
      
      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);
      
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Queued',
      });
      
      const run3 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Also queued',
      });

      // Cancel middle run
      await manager.cancelRun(run2.id);

      // run2 should be removed from queue
      const position2 = await queue.getPosition(run2.id);
      expect(position2).toBeNull();

      // run3 should maintain its relative position
      const position3 = await queue.getPosition(run3.id);
      expect(position3).toBe(0);
    });
  });

  describe('failed run releases lease', () => {
    it('should release lease on failure', async () => {
      const run1 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Will fail',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run1.id);
      await manager.failRun(run1.id, new Error('Test failure'));

      // Verify lease is released
      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);

      // Should be able to start new run
      const run2 = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Next',
      });

      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).not.toBeNull();
    });
  });

  describe('assertSingleActiveRunPerUser helper', () => {
    interface Run { id: string; userId: string; state: RunState; }
    
    function assertSingleActiveRunPerUser(runs: Run[], userId: string): void {
      const activeStates = [RunState.LEASED, RunState.RUNNING];
      const userRuns = runs.filter(r => r.userId === userId);
      const activeRuns = userRuns.filter(r => activeStates.includes(r.state));
      
      expect(activeRuns.length).toBeLessThanOrEqual(1);
    }

    it('should pass with no active runs', () => {
      const runs: Run[] = [
        { id: '1', userId: 'user-1', state: RunState.COMPLETED },
        { id: '2', userId: 'user-1', state: RunState.CANCELLED },
      ];
      
      expect(() => assertSingleActiveRunPerUser(runs, 'user-1')).not.toThrow();
    });

    it('should pass with single active run', () => {
      const runs: Run[] = [
        { id: '1', userId: 'user-1', state: RunState.RUNNING },
        { id: '2', userId: 'user-1', state: RunState.COMPLETED },
      ];
      
      expect(() => assertSingleActiveRunPerUser(runs, 'user-1')).not.toThrow();
    });

    it('should fail with multiple active runs', () => {
      const runs: Run[] = [
        { id: '1', userId: 'user-1', state: RunState.RUNNING },
        { id: '2', userId: 'user-1', state: RunState.LEASED },
      ];
      
      expect(() => assertSingleActiveRunPerUser(runs, 'user-1')).toThrow();
    });
  });
});
