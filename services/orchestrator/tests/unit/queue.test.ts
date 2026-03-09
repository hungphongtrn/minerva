/**
 * Run Queue Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryRunQueue } from '../../src/services/queue.js';

describe('InMemoryRunQueue', () => {
  let queue: InMemoryRunQueue;

  beforeEach(() => {
    queue = new InMemoryRunQueue();
  });

  describe('enqueue', () => {
    it('should add a run to the queue and return position', async () => {
      const position = await queue.enqueue('run-1', 'user-1');
      expect(position).toBe(0);
    });

    it('should maintain FIFO order for multiple runs', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');
      await queue.enqueue('run-3', 'user-1');

      const position1 = await queue.getPosition('run-1');
      const position2 = await queue.getPosition('run-2');
      const position3 = await queue.getPosition('run-3');

      expect(position1).toBe(0);
      expect(position2).toBe(1);
      expect(position3).toBe(2);
    });

    it('should maintain separate queues per user', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-2');

      const user1Length = await queue.getLength('user-1');
      const user2Length = await queue.getLength('user-2');

      expect(user1Length).toBe(1);
      expect(user2Length).toBe(1);
    });
  });

  describe('dequeue', () => {
    it('should return null for empty queue', async () => {
      const result = await queue.dequeue('user-1');
      expect(result).toBeNull();
    });

    it('should return runId in FIFO order', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');

      const first = await queue.dequeue('user-1');
      const second = await queue.dequeue('user-1');

      expect(first).toBe('run-1');
      expect(second).toBe('run-2');
    });

    it('should return null after dequeuing all runs', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.dequeue('user-1');

      const result = await queue.dequeue('user-1');
      expect(result).toBeNull();
    });
  });

  describe('peek', () => {
    it('should return null for empty queue', async () => {
      const result = await queue.peek('user-1');
      expect(result).toBeNull();
    });

    it('should return first run without removing it', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');

      const peeked = await queue.peek('user-1');
      const length = await queue.getLength('user-1');

      expect(peeked).toBe('run-1');
      expect(length).toBe(2);
    });
  });

  describe('remove', () => {
    it('should return false for non-existent run', async () => {
      const result = await queue.remove('run-1');
      expect(result).toBe(false);
    });

    it('should remove run and return true', async () => {
      await queue.enqueue('run-1', 'user-1');
      const result = await queue.remove('run-1');

      expect(result).toBe(true);
      expect(await queue.getLength('user-1')).toBe(0);
    });

    it('should update positions after removal', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');
      await queue.enqueue('run-3', 'user-1');

      await queue.remove('run-2');

      expect(await queue.getPosition('run-1')).toBe(0);
      expect(await queue.getPosition('run-3')).toBe(1);
      expect(await queue.getPosition('run-2')).toBeNull();
    });
  });

  describe('getPosition', () => {
    it('should return null for non-existent run', async () => {
      const position = await queue.getPosition('run-1');
      expect(position).toBeNull();
    });

    it('should return correct position', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');

      expect(await queue.getPosition('run-1')).toBe(0);
      expect(await queue.getPosition('run-2')).toBe(1);
    });
  });

  describe('getLength', () => {
    it('should return 0 for empty queue', async () => {
      expect(await queue.getLength('user-1')).toBe(0);
    });

    it('should return correct length', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-1');

      expect(await queue.getLength('user-1')).toBe(2);
    });
  });

  describe('clear', () => {
    it('should clear all queues', async () => {
      await queue.enqueue('run-1', 'user-1');
      await queue.enqueue('run-2', 'user-2');

      await queue.clear();

      expect(await queue.getLength('user-1')).toBe(0);
      expect(await queue.getLength('user-2')).toBe(0);
    });
  });
});
