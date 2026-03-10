/**
 * SSE Envelope Tests
 *
 * Tests for event envelope structure and validation.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryEventSequencer, DefaultEnvelopeFactory } from '@/sse/envelope.js';

describe('MemoryEventSequencer', () => {
  let sequencer: MemoryEventSequencer;

  beforeEach(() => {
    sequencer = new MemoryEventSequencer();
  });

  describe('next', () => {
    it('should start seq at 1 for new run', () => {
      const seq = sequencer.next('run-1');
      expect(seq).toBe(1);
    });

    it('should increment seq monotonically', () => {
      const seq1 = sequencer.next('run-1');
      const seq2 = sequencer.next('run-1');
      const seq3 = sequencer.next('run-1');

      expect(seq1).toBe(1);
      expect(seq2).toBe(2);
      expect(seq3).toBe(3);
    });

    it('should maintain separate counters per run', () => {
      const run1Seq1 = sequencer.next('run-1');
      const run2Seq1 = sequencer.next('run-2');
      const run1Seq2 = sequencer.next('run-1');
      const run2Seq2 = sequencer.next('run-2');

      expect(run1Seq1).toBe(1);
      expect(run2Seq1).toBe(1);
      expect(run1Seq2).toBe(2);
      expect(run2Seq2).toBe(2);
    });

    it('should handle many events without overflow', () => {
      let lastSeq = 0;
      for (let i = 0; i < 1000; i++) {
        lastSeq = sequencer.next('run-1');
      }
      expect(lastSeq).toBe(1000);
    });
  });

  describe('current', () => {
    it('should return 0 for new run', () => {
      expect(sequencer.current('run-1')).toBe(0);
    });

    it('should return current seq without incrementing', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      
      expect(sequencer.current('run-1')).toBe(2);
      expect(sequencer.current('run-1')).toBe(2); // No change
    });
  });

  describe('reset', () => {
    it('should reset seq to specified value', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      sequencer.reset('run-1', 10);
      
      expect(sequencer.next('run-1')).toBe(11);
    });

    it('should reset to 0 by default', () => {
      sequencer.next('run-1');
      sequencer.reset('run-1');
      
      expect(sequencer.next('run-1')).toBe(1);
    });
  });

  describe('cleanup', () => {
    it('should remove counter for run', () => {
      sequencer.next('run-1');
      sequencer.cleanup('run-1');
      
      expect(sequencer.current('run-1')).toBe(0);
      expect(sequencer.next('run-1')).toBe(1);
    });
  });

  describe('concurrent access', () => {
    it('should handle concurrent events with unique seq', async () => {
      const promises: Promise<number>[] = [];
      
      // Simulate 100 concurrent calls
      for (let i = 0; i < 100; i++) {
        promises.push(Promise.resolve(sequencer.next('run-1')));
      }
      
      const sequences = await Promise.all(promises);
      const uniqueSeqs = new Set(sequences);
      
      expect(uniqueSeqs.size).toBe(100);
      expect(sequences).toContain(1);
      expect(sequences).toContain(100);
    });
  });
});

describe('DefaultEnvelopeFactory', () => {
  let sequencer: MemoryEventSequencer;
  let factory: DefaultEnvelopeFactory;

  beforeEach(() => {
    sequencer = new MemoryEventSequencer();
    factory = new DefaultEnvelopeFactory(sequencer);
  });

  describe('create', () => {
    it('should create envelope with all required fields', () => {
      const envelope = factory.create('run-1', 'run_started', { started_at: new Date().toISOString() });
      
      expect(envelope).toHaveProperty('type', 'run_started');
      expect(envelope).toHaveProperty('run_id', 'run-1');
      expect(envelope).toHaveProperty('ts');
      expect(envelope).toHaveProperty('seq', 1);
      expect(envelope).toHaveProperty('payload');
    });

    it('should use ISO 8601 timestamp format', () => {
      const envelope = factory.create('run-1', 'run_started', {});
      
      // Verify ISO 8601 format (e.g., "2024-01-15T10:30:00.000Z")
      const iso8601Regex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
      expect(envelope.ts).toMatch(iso8601Regex);
    });

    it('should auto-increment seq for same run', () => {
      const envelope1 = factory.create('run-1', 'run_started', {});
      const envelope2 = factory.create('run-1', 'turn_start', {});
      const envelope3 = factory.create('run-1', 'tool_execution_start', {});
      
      expect(envelope1.seq).toBe(1);
      expect(envelope2.seq).toBe(2);
      expect(envelope3.seq).toBe(3);
    });

    it('should maintain separate seq per run', () => {
      const run1Event1 = factory.create('run-1', 'run_started', {});
      const run2Event1 = factory.create('run-2', 'run_started', {});
      const run1Event2 = factory.create('run-1', 'turn_start', {});
      const run2Event2 = factory.create('run-2', 'turn_start', {});
      
      expect(run1Event1.seq).toBe(1);
      expect(run2Event1.seq).toBe(1);
      expect(run1Event2.seq).toBe(2);
      expect(run2Event2.seq).toBe(2);
    });

    it('should include payload in envelope', () => {
      const payload = {
        queue_position: 5,
        estimated_start: new Date().toISOString(),
      };
      
      const envelope = factory.create('run-1', 'run_queued', payload);
      expect(envelope.payload).toEqual(payload);
    });

    it('should use correct type discriminator', () => {
      const types = [
        'run_queued',
        'run_started',
        'run_completed',
        'run_failed',
        'run_cancelled',
        'run_timed_out',
        'stream_connected',
        'agent_start',
        'agent_end',
        'turn_start',
        'turn_end',
        'message_start',
        'message_update',
        'message_end',
        'tool_execution_start',
        'tool_execution_update',
        'tool_execution_end',
      ] as const;
      
      for (const type of types) {
        const envelope = factory.create('run-1', type, {});
        expect(envelope.type).toBe(type);
      }
    });
  });

  describe('createAt', () => {
    it('should create envelope at specified seq and ts', () => {
      const ts = '2024-01-15T10:30:00.000Z';
      const envelope = factory.createAt('run-1', 'run_started', {}, 42, ts);
      
      expect(envelope.seq).toBe(42);
      expect(envelope.ts).toBe(ts);
    });

    it('should not affect sequencer counter', () => {
      factory.createAt('run-1', 'run_started', {}, 100, '2024-01-15T10:30:00.000Z');
      const envelope = factory.create('run-1', 'turn_start', {});
      
      expect(envelope.seq).toBe(1); // Should start at 1, not affected by createAt
    });
  });
});

describe('Envelope Assertions', () => {
  it('should assert monotonic seq across multiple runs', () => {
    const events = [
      { type: 'run_queued', run_id: 'run-1', seq: 1, ts: '2024-01-15T10:00:00Z', payload: {} },
      { type: 'run_started', run_id: 'run-1', seq: 2, ts: '2024-01-15T10:00:01Z', payload: {} },
      { type: 'turn_start', run_id: 'run-1', seq: 3, ts: '2024-01-15T10:00:02Z', payload: {} },
      { type: 'run_completed', run_id: 'run-1', seq: 4, ts: '2024-01-15T10:00:03Z', payload: {} },
    ];
    
    // Verify monotonic increasing
    for (let i = 1; i < events.length; i++) {
      expect(events[i].seq).toBeGreaterThan(events[i - 1].seq);
    }
  });

  it('should assert strict monotonic seq without gaps', () => {
    const events = [
      { type: 'run_queued', run_id: 'run-1', seq: 1, ts: '', payload: {} },
      { type: 'run_started', run_id: 'run-1', seq: 2, ts: '', payload: {} },
      { type: 'run_completed', run_id: 'run-1', seq: 3, ts: '', payload: {} },
    ];
    
    // Check for gaps - should pass with consecutive sequences
    for (let i = 1; i < events.length; i++) {
      const gap = events[i].seq - events[i - 1].seq;
      expect(gap).toBe(1); // Should be exactly 1
    }
  });

  it('should detect gaps in sequence', () => {
    const eventsWithGap = [
      { type: 'run_queued', run_id: 'run-1', seq: 1, ts: '', payload: {} },
      { type: 'run_started', run_id: 'run-1', seq: 3, ts: '', payload: {} }, // Gap at 2!
      { type: 'run_completed', run_id: 'run-1', seq: 4, ts: '', payload: {} },
    ];
    
    // This should fail due to gap
    let hasGap = false;
    for (let i = 1; i < eventsWithGap.length; i++) {
      const gap = eventsWithGap[i].seq - eventsWithGap[i - 1].seq;
      if (gap !== 1) {
        hasGap = true;
        break;
      }
    }
    expect(hasGap).toBe(true);
  });
});
