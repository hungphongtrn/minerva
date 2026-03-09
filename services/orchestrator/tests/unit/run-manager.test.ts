/**
 * Run Manager Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  RunManager,
  InMemoryRunRepository,
  InMemoryRunQueue,
  InMemoryLeaseManager,
  InMemoryCancellationRegistry,
  InMemoryTimeoutManager,
} from '../../src/services/index.js';
import { RunState } from '../../src/types/run.js';
import { RunNotFoundError, InvalidStateTransitionError } from '../../src/types/errors.js';

describe('RunManager', () => {
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
      { defaultTimeoutMs: 10000, leaseTtlMs: 30000 }
    );
  });

  describe('createRun', () => {
    it('should create run with correct initial state', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      expect(run.id).toBeDefined();
      expect(run.userId).toBe('user-1');
      expect(run.state).toBe(RunState.QUEUED);
      expect(run.agentPackId).toBe('pack-1');
      expect(run.prompt).toBe('Hello');
      expect(run.queuePosition).toBe(0);
    });

    it('should add run to queue', async () => {
      await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const queueLength = await queue.getLength('user-1');
      expect(queueLength).toBe(1);
    });

    it('should use default timeout when not specified', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      expect(run.maxDurationMs).toBe(10000);
    });

    it('should respect specified timeout', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
        maxDurationMs: 5000,
      });

      expect(run.maxDurationMs).toBe(5000);
    });

    it('should cap timeout at max', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
        maxDurationMs: 999999999,
      });

      expect(run.maxDurationMs).toBe(3600000); // MAX_RUN_TIMEOUT_MS
    });
  });

  describe('getRun', () => {
    it('should return run by id', async () => {
      const created = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const retrieved = await manager.getRun(created.id);
      expect(retrieved).not.toBeNull();
      expect(retrieved!.id).toBe(created.id);
    });

    it('should return null for non-existent run', async () => {
      const run = await manager.getRun('non-existent');
      expect(run).toBeNull();
    });
  });

  describe('getUserRuns', () => {
    it('should return all runs for user', async () => {
      await manager.createRun({ userId: 'user-1', agentPackId: 'pack-1', prompt: 'Hello 1' });
      await manager.createRun({ userId: 'user-1', agentPackId: 'pack-1', prompt: 'Hello 2' });
      await manager.createRun({ userId: 'user-2', agentPackId: 'pack-1', prompt: 'Hello 3' });

      const user1Runs = await manager.getUserRuns('user-1');
      expect(user1Runs).toHaveLength(2);
    });
  });

  describe('transitionState', () => {
    it('should transition run to new state', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const transitioned = await manager.transitionState(run.id, RunState.CANCELLED);
      expect(transitioned.state).toBe(RunState.CANCELLED);
    });

    it('should throw for non-existent run', async () => {
      await expect(
        manager.transitionState('non-existent', RunState.CANCELLED)
      ).rejects.toThrow(RunNotFoundError);
    });

    it('should throw for invalid transition', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await expect(
        manager.transitionState(run.id, RunState.COMPLETED)
      ).rejects.toThrow(InvalidStateTransitionError);
    });

    it('should set completedAt for terminal states', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const transitioned = await manager.transitionState(run.id, RunState.CANCELLED);
      expect(transitioned.completedAt).toBeInstanceOf(Date);
    });

    it('should set startedAt when transitioning to RUNNING', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      // First transition to LEASED
      await manager.transitionState(run.id, RunState.LEASED);
      
      // Then to RUNNING
      const transitioned = await manager.transitionState(run.id, RunState.RUNNING);
      expect(transitioned.startedAt).toBeInstanceOf(Date);
    });
  });

  describe('acquireNextRun', () => {
    it('should return null when queue is empty', async () => {
      const run = await manager.acquireNextRun('user-1');
      expect(run).toBeNull();
    });

    it('should acquire next run from queue', async () => {
      const created = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const acquired = await manager.acquireNextRun('user-1');
      expect(acquired).not.toBeNull();
      expect(acquired!.id).toBe(created.id);
      expect(acquired!.state).toBe(RunState.LEASED);
      expect(acquired!.leaseToken).toBeDefined();
    });

    it('should remove run from queue after acquisition', async () => {
      await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      const queueLength = await queue.getLength('user-1');
      expect(queueLength).toBe(0);
    });

    it('should not acquire if another run has lease', async () => {
      await manager.createRun({ userId: 'user-1', agentPackId: 'pack-1', prompt: 'Hello 1' });
      await manager.createRun({ userId: 'user-1', agentPackId: 'pack-1', prompt: 'Hello 2' });

      await manager.acquireNextRun('user-1');
      const second = await manager.acquireNextRun('user-1');

      expect(second).toBeNull();
    });
  });

  describe('startRun', () => {
    it('should transition run to RUNNING', async () => {
      const created = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      const started = await manager.startRun(created.id);

      expect(started.state).toBe(RunState.RUNNING);
    });

    it('should create cancellation context', async () => {
      const created = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(created.id);

      expect(cancellationRegistry.get(created.id)).toBeDefined();
    });

    it('should schedule timeout', async () => {
      const created = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(created.id);

      expect(timeoutManager.has(created.id)).toBe(true);
    });
  });

  describe('cancelRun', () => {
    it('should cancel queued run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const cancelled = await manager.cancelRun(run.id);
      expect(cancelled.state).toBe(RunState.CANCELLED);
    });

    it('should remove cancelled run from queue', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.cancelRun(run.id);
      const position = await queue.getPosition(run.id);
      expect(position).toBeNull();
    });

    it('should cancel running run and release lease', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      await manager.cancelRun(run.id);
      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);
    });

    it('should signal cancellation', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      await manager.cancelRun(run.id, 'test reason');
      expect(manager.isCancelled(run.id)).toBe(true);
    });

    it('should return run if already in terminal state', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.cancelRun(run.id);
      const result = await manager.cancelRun(run.id);
      
      expect(result.state).toBe(RunState.CANCELLED);
    });
  });

  describe('completeRun', () => {
    it('should complete running run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      const completed = await manager.completeRun(run.id);
      expect(completed.state).toBe(RunState.COMPLETED);
    });

    it('should release lease on completion', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);
      await manager.completeRun(run.id);

      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);
    });

    it('should clean up cancellation context', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);
      await manager.completeRun(run.id);

      expect(cancellationRegistry.get(run.id)).toBeUndefined();
    });
  });

  describe('failRun', () => {
    it('should fail running run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      const failed = await manager.failRun(run.id, new Error('Something went wrong'));
      expect(failed.state).toBe(RunState.FAILED);
      expect(failed.error).toBe('Something went wrong');
    });

    it('should accept string error', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      const failed = await manager.failRun(run.id, 'Custom error');
      expect(failed.error).toBe('Custom error');
    });
  });

  describe('getCancellationSignal', () => {
    it('should return signal for running run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      const signal = manager.getCancellationSignal(run.id);
      expect(signal).toBeDefined();
    });

    it('should return undefined for non-running run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const signal = manager.getCancellationSignal(run.id);
      expect(signal).toBeUndefined();
    });
  });

  describe('toMetadata', () => {
    it('should convert run to metadata', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
      });

      const metadata = manager.toMetadata(run);

      expect(metadata.runId).toBe(run.id);
      expect(metadata.state).toBe(run.state);
      expect(metadata.createdAt).toBe(run.createdAt.toISOString());
      expect(metadata.queuePosition).toBe(0);
    });
  });

  describe('timeout enforcement', () => {
    it('should timeout long-running run', async () => {
      const run = await manager.createRun({
        userId: 'user-1',
        agentPackId: 'pack-1',
        prompt: 'Hello',
        maxDurationMs: 50, // Short timeout for testing
      });

      await manager.acquireNextRun('user-1');
      await manager.startRun(run.id);

      // Wait for timeout
      await new Promise((resolve) => setTimeout(resolve, 100));

      const timedOut = await manager.getRun(run.id);
      expect(timedOut!.state).toBe(RunState.TIMED_OUT);
    });
  });
});
