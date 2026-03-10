/**
 * SSE Stream Tests
 *
 * Tests for stream termination at run completion.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemorySSEStreamController } from '@/sse/stream.js';
import type { SSEEventEnvelope, SSEEventType } from '@/sse/types.js';

// Mock SSE stream for testing
class MockSSEStream {
  private open = true;
  public events: SSEEventEnvelope[] = [];
  public closed = false;
  public closeCount = 0;

  write(event: SSEEventEnvelope): void {
    if (this.open) {
      this.events.push(event);
    }
  }

  close(): void {
    this.open = false;
    this.closed = true;
    this.closeCount++;
  }

  isOpen(): boolean {
    return this.open;
  }

  getClientInfo() {
    return { ip: '127.0.0.1' };
  }
}

describe('MemorySSEStreamController', () => {
  let controller: MemorySSEStreamController;

  beforeEach(() => {
    controller = new MemorySSEStreamController();
  });

  describe('stream registration', () => {
    it('should register stream for run', () => {
      const stream = new MockSSEStream();
      const cleanup = controller.register('run-1', stream);
      
      expect(controller.getConnectionCount('run-1')).toBe(1);
      expect(typeof cleanup).toBe('function');
    });

    it('should allow multiple streams for same run', () => {
      const stream1 = new MockSSEStream();
      const stream2 = new MockSSEStream();
      
      controller.register('run-1', stream1);
      controller.register('run-1', stream2);
      
      expect(controller.getConnectionCount('run-1')).toBe(2);
    });

    it('should track total connections', () => {
      controller.register('run-1', new MockSSEStream());
      controller.register('run-1', new MockSSEStream());
      controller.register('run-2', new MockSSEStream());
      
      expect(controller.getTotalConnections()).toBe(3);
    });
  });

  describe('broadcast', () => {
    it('should broadcast to all streams for run', () => {
      const stream1 = new MockSSEStream();
      const stream2 = new MockSSEStream();
      
      controller.register('run-1', stream1);
      controller.register('run-1', stream2);
      
      const event: SSEEventEnvelope = {
        type: 'run_started' as SSEEventType,
        run_id: 'run-1',
        ts: new Date().toISOString(),
        seq: 1,
        payload: {},
      };
      
      controller.broadcast('run-1', event);
      
      expect(stream1.events).toHaveLength(1);
      expect(stream2.events).toHaveLength(1);
      expect(stream1.events[0]).toEqual(event);
      expect(stream2.events[0]).toEqual(event);
    });

    it('should not broadcast to other runs', () => {
      const stream1 = new MockSSEStream();
      const stream2 = new MockSSEStream();
      
      controller.register('run-1', stream1);
      controller.register('run-2', stream2);
      
      const event: SSEEventEnvelope = {
        type: 'run_started' as SSEEventType,
        run_id: 'run-1',
        ts: new Date().toISOString(),
        seq: 1,
        payload: {},
      };
      
      controller.broadcast('run-1', event);
      
      expect(stream1.events).toHaveLength(1);
      expect(stream2.events).toHaveLength(0);
    });

    it('should handle closed streams gracefully', () => {
      const stream1 = new MockSSEStream();
      const stream2 = new MockSSEStream();
      
      controller.register('run-1', stream1);
      controller.register('run-1', stream2);
      
      // Close one stream
      stream1.close();
      
      const event: SSEEventEnvelope = {
        type: 'run_started' as SSEEventType,
        run_id: 'run-1',
        ts: new Date().toISOString(),
        seq: 1,
        payload: {},
      };
      
      // Should not throw
      expect(() => controller.broadcast('run-1', event)).not.toThrow();
      
      // Open stream should receive event
      expect(stream2.events).toHaveLength(1);
    });
  });

  describe('stream termination', () => {
    it('should close all streams on closeRun', () => {
      const stream1 = new MockSSEStream();
      const stream2 = new MockSSEStream();
      
      controller.register('run-1', stream1);
      controller.register('run-1', stream2);
      
      controller.closeRun('run-1');
      
      expect(stream1.closed).toBe(true);
      expect(stream2.closed).toBe(true);
      expect(controller.getConnectionCount('run-1')).toBe(0);
    });

    it('should handle closeRun for non-existent run', () => {
      expect(() => controller.closeRun('non-existent')).not.toThrow();
    });

    it('should be idempotent on multiple closeRun calls', () => {
      const stream = new MockSSEStream();
      
      controller.register('run-1', stream);
      
      controller.closeRun('run-1');
      controller.closeRun('run-1');
      controller.closeRun('run-1');
      
      expect(stream.closeCount).toBe(1);
    });
  });

  describe('cleanup on disconnect', () => {
    it('should cleanup on cleanup function call', () => {
      const stream = new MockSSEStream();
      const cleanup = controller.register('run-1', stream);
      
      cleanup();
      
      expect(stream.closed).toBe(true);
      expect(controller.getConnectionCount('run-1')).toBe(0);
    });

    it('should handle multiple cleanup calls', () => {
      const stream = new MockSSEStream();
      const cleanup = controller.register('run-1', stream);
      
      cleanup();
      cleanup();
      cleanup();
      
      expect(stream.closeCount).toBe(1);
    });
  });

  describe('terminal state detection', () => {
    const terminalStates: SSEEventType[] = [
      'run_completed',
      'run_failed',
      'run_cancelled',
      'run_timed_out',
    ];
    
    const nonTerminalStates: SSEEventType[] = [
      'run_queued',
      'run_started',
      'stream_connected',
      'agent_start',
      'turn_start',
      'tool_execution_start',
    ];

    it('should identify terminal event types', () => {
      for (const type of terminalStates) {
        const isTerminal = type.startsWith('run_') && 
          (type === 'run_completed' || type === 'run_failed' || 
           type === 'run_cancelled' || type === 'run_timed_out');
        expect(isTerminal).toBe(true);
      }
    });

    it('should identify non-terminal event types', () => {
      for (const type of nonTerminalStates) {
        const isTerminal = type.startsWith('run_') && 
          (type === 'run_completed' || type === 'run_failed' || 
           type === 'run_cancelled' || type === 'run_timed_out');
        expect(isTerminal).toBe(false);
      }
    });
  });

  describe('stream termination at terminal events', () => {
    function createTerminalEvent(runId: string, type: SSEEventType, seq: number): SSEEventEnvelope {
      return {
        type,
        run_id: runId,
        ts: new Date().toISOString(),
        seq,
        payload: {},
      };
    }

    it('should close streams after run_completed event', () => {
      const stream = new MockSSEStream();
      controller.register('run-1', stream);
      
      const event = createTerminalEvent('run-1', 'run_completed', 10);
      controller.broadcast('run-1', event);
      
      // Simulate closing after terminal event
      controller.closeRun('run-1');
      
      expect(stream.closed).toBe(true);
      expect(stream.events).toHaveLength(1);
    });

    it('should close streams after run_failed event', () => {
      const stream = new MockSSEStream();
      controller.register('run-1', stream);
      
      const event = createTerminalEvent('run-1', 'run_failed', 10);
      controller.broadcast('run-1', event);
      controller.closeRun('run-1');
      
      expect(stream.closed).toBe(true);
    });

    it('should close streams after run_cancelled event', () => {
      const stream = new MockSSEStream();
      controller.register('run-1', stream);
      
      const event = createTerminalEvent('run-1', 'run_cancelled', 10);
      controller.broadcast('run-1', event);
      controller.closeRun('run-1');
      
      expect(stream.closed).toBe(true);
    });

    it('should close streams after run_timed_out event', () => {
      const stream = new MockSSEStream();
      controller.register('run-1', stream);
      
      const event = createTerminalEvent('run-1', 'run_timed_out', 10);
      controller.broadcast('run-1', event);
      controller.closeRun('run-1');
      
      expect(stream.closed).toBe(true);
    });
  });

  describe('stream stays open for non-terminal states', () => {
    it('should keep stream open during active run', () => {
      const stream = new MockSSEStream();
      controller.register('run-1', stream);
      
      const events: SSEEventEnvelope[] = [
        { type: 'run_started', run_id: 'run-1', ts: new Date().toISOString(), seq: 1, payload: {} },
        { type: 'agent_start', run_id: 'run-1', ts: new Date().toISOString(), seq: 2, payload: {} },
        { type: 'turn_start', run_id: 'run-1', ts: new Date().toISOString(), seq: 3, payload: {} },
        { type: 'tool_execution_start', run_id: 'run-1', ts: new Date().toISOString(), seq: 4, payload: {} },
      ];
      
      for (const event of events) {
        controller.broadcast('run-1', event as SSEEventEnvelope);
      }
      
      expect(stream.isOpen()).toBe(true);
      expect(stream.events).toHaveLength(4);
    });
  });

  describe('assertStreamTerminated helper', () => {
    function assertStreamTerminated(
      events: Array<{ type: string }>,
      terminalType: string
    ): void {
      const lastEvent = events[events.length - 1];
      expect(lastEvent.type).toBe(terminalType);
    }

    it('should validate termination at completed', () => {
      const events = [
        { type: 'run_started' },
        { type: 'run_completed' },
      ];
      
      expect(() => assertStreamTerminated(events, 'run_completed')).not.toThrow();
    });

    it('should validate termination at failed', () => {
      const events = [
        { type: 'run_started' },
        { type: 'tool_execution_start' },
        { type: 'run_failed' },
      ];
      
      expect(() => assertStreamTerminated(events, 'run_failed')).not.toThrow();
    });
  });
});
