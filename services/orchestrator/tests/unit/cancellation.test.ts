/**
 * Cancellation Registry Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryCancellationRegistry } from '../../src/services/cancellation.js';

describe('InMemoryCancellationRegistry', () => {
  let registry: InMemoryCancellationRegistry;

  beforeEach(() => {
    registry = new InMemoryCancellationRegistry();
  });

  describe('create', () => {
    it('should create cancellation context for run', () => {
      const context = registry.create('run-1');

      expect(context.runId).toBe('run-1');
      expect(context.controller).toBeDefined();
      expect(context.signal).toBeDefined();
      expect(context.isCancelled).toBe(false);
    });

    it('should replace existing context', () => {
      const context1 = registry.create('run-1');
      context1.cancel('first');

      const context2 = registry.create('run-1');
      expect(context2.isCancelled).toBe(false);
      expect(registry.get('run-1')!.isCancelled).toBe(false);
    });
  });

  describe('get', () => {
    it('should return undefined for non-existent run', () => {
      expect(registry.get('run-1')).toBeUndefined();
    });

    it('should return context for existing run', () => {
      registry.create('run-1');
      const context = registry.get('run-1');

      expect(context).toBeDefined();
      expect(context!.runId).toBe('run-1');
    });
  });

  describe('remove', () => {
    it('should remove context', () => {
      registry.create('run-1');
      registry.remove('run-1');

      expect(registry.get('run-1')).toBeUndefined();
    });

    it('should handle removing non-existent run', () => {
      expect(() => registry.remove('run-1')).not.toThrow();
    });
  });

  describe('cancel', () => {
    it('should return false for non-existent run', () => {
      expect(registry.cancel('run-1')).toBe(false);
    });

    it('should cancel run and return true', () => {
      registry.create('run-1');
      const result = registry.cancel('run-1', 'test reason');

      expect(result).toBe(true);
      expect(registry.isCancelled('run-1')).toBe(true);
      expect(registry.get('run-1')!.cancelReason).toBe('test reason');
    });

    it('should abort the signal when cancelled', () => {
      const context = registry.create('run-1');
      let aborted = false;
      let abortReason: string | undefined;

      context.signal.addEventListener('abort', () => {
        aborted = true;
        abortReason = context.signal.reason;
      });

      registry.cancel('run-1', 'test reason');

      expect(aborted).toBe(true);
      expect(abortReason).toBe('test reason');
    });

    it('should handle multiple cancels gracefully', () => {
      registry.create('run-1');
      registry.cancel('run-1', 'first');
      registry.cancel('run-1', 'second');

      expect(registry.get('run-1')!.cancelReason).toBe('first');
    });
  });

  describe('cancelAll', () => {
    it('should cancel all active runs', () => {
      registry.create('run-1');
      registry.create('run-2');
      registry.create('run-3');

      registry.cancelAll('shutdown');

      expect(registry.isCancelled('run-1')).toBe(true);
      expect(registry.isCancelled('run-2')).toBe(true);
      expect(registry.isCancelled('run-3')).toBe(true);
    });

    it('should handle empty registry', () => {
      expect(() => registry.cancelAll()).not.toThrow();
    });
  });

  describe('isCancelled', () => {
    it('should return false for non-existent run', () => {
      expect(registry.isCancelled('run-1')).toBe(false);
    });

    it('should return false for active run', () => {
      registry.create('run-1');
      expect(registry.isCancelled('run-1')).toBe(false);
    });

    it('should return true for cancelled run', () => {
      registry.create('run-1');
      registry.cancel('run-1');
      expect(registry.isCancelled('run-1')).toBe(true);
    });
  });

  describe('getActiveRunIds', () => {
    it('should return empty array for empty registry', () => {
      expect(registry.getActiveRunIds()).toEqual([]);
    });

    it('should return all run IDs', () => {
      registry.create('run-1');
      registry.create('run-2');

      const ids = registry.getActiveRunIds();
      expect(ids).toContain('run-1');
      expect(ids).toContain('run-2');
      expect(ids).toHaveLength(2);
    });
  });

  describe('signal propagation', () => {
    it('should propagate abort to async operations', async () => {
      const context = registry.create('run-1');

      // Simulate an async operation that checks the signal
      const asyncOp = async () => {
        return new Promise((resolve, reject) => {
          if (context.signal.aborted) {
            reject(new Error('Aborted'));
            return;
          }

          context.signal.addEventListener('abort', () => {
            reject(new Error('Aborted: ' + context.signal.reason));
          });

          // Simulate work
          setTimeout(() => resolve('completed'), 100);
        });
      };

      // Cancel after a short delay
      setTimeout(() => registry.cancel('run-1', 'test'), 10);

      await expect(asyncOp()).rejects.toThrow('Aborted: test');
    });
  });
});
