/**
 * Timeout Manager Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryTimeoutManager } from '../../src/services/timeout.js';

describe('InMemoryTimeoutManager', () => {
  let manager: InMemoryTimeoutManager;

  beforeEach(() => {
    manager = new InMemoryTimeoutManager();
  });

  describe('schedule', () => {
    it('should schedule timeout and return handle', () => {
      const handle = manager.schedule('run-1', 1000, () => {});

      expect(handle.runId).toBe('run-1');
      expect(handle.scheduledAt).toBeInstanceOf(Date);
      expect(handle.timeoutAt).toBeInstanceOf(Date);
    });

    it('should call callback after delay', async () => {
      let called = false;
      let calledRunId: string | undefined;

      manager.schedule('run-1', 10, (runId) => {
        called = true;
        calledRunId = runId;
      });

      await new Promise((resolve) => setTimeout(resolve, 50));

      expect(called).toBe(true);
      expect(calledRunId).toBe('run-1');
    });

    it('should replace existing timeout for same run', async () => {
      let firstCalled = false;
      let secondCalled = false;

      manager.schedule('run-1', 100, () => {
        firstCalled = true;
      });

      manager.schedule('run-1', 10, () => {
        secondCalled = true;
      });

      await new Promise((resolve) => setTimeout(resolve, 50));

      expect(firstCalled).toBe(false);
      expect(secondCalled).toBe(true);
    });
  });

  describe('clear', () => {
    it('should return false for non-existent run', () => {
      expect(manager.clear('run-1')).toBe(false);
    });

    it('should clear scheduled timeout', async () => {
      let called = false;

      manager.schedule('run-1', 10, () => {
        called = true;
      });

      const cleared = manager.clear('run-1');
      expect(cleared).toBe(true);

      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(called).toBe(false);
    });
  });

  describe('has', () => {
    it('should return false for non-existent run', () => {
      expect(manager.has('run-1')).toBe(false);
    });

    it('should return true for scheduled run', () => {
      manager.schedule('run-1', 1000, () => {});
      expect(manager.has('run-1')).toBe(true);
    });

    it('should return false after timeout fires', async () => {
      manager.schedule('run-1', 10, () => {});
      await new Promise((resolve) => setTimeout(resolve, 50));

      expect(manager.has('run-1')).toBe(false);
    });
  });

  describe('getTimeoutAt', () => {
    it('should return null for non-existent run', () => {
      expect(manager.getTimeoutAt('run-1')).toBeNull();
    });

    it('should return scheduled timeout time', () => {
      const handle = manager.schedule('run-1', 1000, () => {});
      const timeoutAt = manager.getTimeoutAt('run-1');

      expect(timeoutAt).toBeInstanceOf(Date);
      expect(timeoutAt!.getTime()).toBe(handle.timeoutAt.getTime());
    });
  });

  describe('clearAll', () => {
    it('should clear all timeouts', async () => {
      let called1 = false;
      let called2 = false;

      manager.schedule('run-1', 10, () => { called1 = true; });
      manager.schedule('run-2', 10, () => { called2 = true; });

      manager.clearAll();

      await new Promise((resolve) => setTimeout(resolve, 50));

      expect(called1).toBe(false);
      expect(called2).toBe(false);
    });
  });

  describe('getScheduledRunIds', () => {
    it('should return empty array initially', () => {
      expect(manager.getScheduledRunIds()).toEqual([]);
    });

    it('should return scheduled run IDs', () => {
      manager.schedule('run-1', 1000, () => {});
      manager.schedule('run-2', 1000, () => {});

      const ids = manager.getScheduledRunIds();
      expect(ids).toContain('run-1');
      expect(ids).toContain('run-2');
      expect(ids).toHaveLength(2);
    });
  });

  describe('async callback', () => {
    it('should handle async callbacks', async () => {
      let asyncCompleted = false;

      manager.schedule('run-1', 10, async () => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        asyncCompleted = true;
      });

      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(asyncCompleted).toBe(true);
    });
  });
});
