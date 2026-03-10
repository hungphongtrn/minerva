/**
 * SSE Sequencer Tests
 *
 * Tests for sequence number generation and monotonicity.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryEventSequencer } from '@/sse/envelope.js';

describe('MemoryEventSequencer', () => {
  let sequencer: MemoryEventSequencer;

  beforeEach(() => {
    sequencer = new MemoryEventSequencer();
  });

  describe('sequence initialization', () => {
    it('should start seq at 1 for new run', () => {
      const seq = sequencer.next('run-1');
      expect(seq).toBe(1);
    });

    it('should return 0 for current on new run', () => {
      expect(sequencer.current('run-1')).toBe(0);
    });
  });

  describe('monotonic increments', () => {
    it('should increment seq by 1 for each event', () => {
      const seq1 = sequencer.next('run-1');
      const seq2 = sequencer.next('run-1');
      const seq3 = sequencer.next('run-1');
      const seq4 = sequencer.next('run-1');

      expect(seq2).toBe(seq1 + 1);
      expect(seq3).toBe(seq2 + 1);
      expect(seq4).toBe(seq3 + 1);
    });

    it('should maintain strict monotonicity (no gaps or duplicates)', () => {
      const sequences: number[] = [];
      
      for (let i = 0; i < 50; i++) {
        sequences.push(sequencer.next('run-1'));
      }
      
      // Verify no duplicates
      const uniqueSequences = new Set(sequences);
      expect(uniqueSequences.size).toBe(sequences.length);
      
      // Verify consecutive integers
      for (let i = 0; i < sequences.length; i++) {
        expect(sequences[i]).toBe(i + 1);
      }
    });
  });

  describe('per-run isolation', () => {
    it('should maintain separate counters per run', () => {
      const run1Events: number[] = [];
      const run2Events: number[] = [];
      const run3Events: number[] = [];
      
      // Interleave events between runs
      for (let i = 0; i < 10; i++) {
        run1Events.push(sequencer.next('run-1'));
        run2Events.push(sequencer.next('run-2'));
        run3Events.push(sequencer.next('run-3'));
      }
      
      // Each run should have seq 1-10
      expect(run1Events).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      expect(run2Events).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      expect(run3Events).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    });

    it('should not be affected by other runs', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      
      expect(sequencer.current('run-2')).toBe(0);
      expect(sequencer.next('run-2')).toBe(1);
      
      expect(sequencer.next('run-1')).toBe(3);
    });
  });

  describe('reset functionality', () => {
    it('should reset seq to specified value', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      sequencer.reset('run-1', 100);
      
      expect(sequencer.next('run-1')).toBe(101);
      expect(sequencer.next('run-1')).toBe(102);
    });

    it('should reset to 0 by default', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      sequencer.reset('run-1');
      
      expect(sequencer.next('run-1')).toBe(1);
    });

    it('should allow reset to arbitrary values', () => {
      sequencer.reset('run-1', 42);
      expect(sequencer.next('run-1')).toBe(43);
      
      sequencer.reset('run-1', 0);
      expect(sequencer.next('run-1')).toBe(1);
      
      sequencer.reset('run-1', 999);
      expect(sequencer.next('run-1')).toBe(1000);
    });
  });

  describe('cleanup', () => {
    it('should remove counter for run', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      sequencer.cleanup('run-1');
      
      expect(sequencer.current('run-1')).toBe(0);
    });

    it('should start fresh after cleanup', () => {
      sequencer.next('run-1');
      sequencer.next('run-1');
      sequencer.cleanup('run-1');
      
      expect(sequencer.next('run-1')).toBe(1);
      expect(sequencer.current('run-1')).toBe(1);
    });

    it('should not affect other runs during cleanup', () => {
      sequencer.next('run-1');
      sequencer.next('run-2');
      sequencer.next('run-1');
      
      sequencer.cleanup('run-1');
      
      expect(sequencer.current('run-2')).toBe(1);
      expect(sequencer.next('run-2')).toBe(2);
    });
  });

  describe('concurrent safety', () => {
    it('should handle concurrent calls without duplicates', async () => {
      const promises: Promise<number>[] = [];
      
      // Create 100 concurrent calls
      for (let i = 0; i < 100; i++) {
        promises.push(Promise.resolve(sequencer.next('run-1')));
      }
      
      const results = await Promise.all(promises);
      const uniqueResults = new Set(results);
      
      expect(uniqueResults.size).toBe(100);
      expect(results.sort((a, b) => a - b)).toEqual(
        Array.from({ length: 100 }, (_, i) => i + 1)
      );
    });

    it('should maintain monotonicity under concurrent load', async () => {
      const runs = ['run-1', 'run-2', 'run-3'];
      const allPromises: Promise<{ runId: string; seq: number }>[] = [];
      
      // Create concurrent calls across multiple runs
      for (let i = 0; i < 50; i++) {
        for (const runId of runs) {
          allPromises.push(
            Promise.resolve({ runId, seq: sequencer.next(runId) })
          );
        }
      }
      
      const results = await Promise.all(allPromises);
      
      // Group by run and verify monotonicity
      for (const runId of runs) {
        const runSequences = results
          .filter(r => r.runId === runId)
          .map(r => r.seq)
          .sort((a, b) => a - b);
        
        expect(runSequences).toEqual(
          Array.from({ length: 50 }, (_, i) => i + 1)
        );
      }
    });
  });

  describe('memory management', () => {
    it('should not grow unbounded after cleanup', () => {
      // Simulate many runs
      for (let i = 0; i < 100; i++) {
        sequencer.next(`run-${i}`);
      }
      
      // Cleanup half of them
      for (let i = 0; i < 50; i++) {
        sequencer.cleanup(`run-${i}`);
      }
      
      // Verify cleaned runs are gone
      for (let i = 0; i < 50; i++) {
        expect(sequencer.current(`run-${i}`)).toBe(0);
      }
      
      // Verify remaining runs still work
      for (let i = 50; i < 100; i++) {
        expect(sequencer.current(`run-${i}`)).toBe(1);
      }
    });
  });
});

describe('Sequence Monotonicity Assertions', () => {
  function assertMonotonicSeq(events: Array<{ seq: number }>, strict = true): void {
    for (let i = 1; i < events.length; i++) {
      if (strict) {
        expect(events[i].seq).toBe(events[i - 1].seq + 1);
      } else {
        expect(events[i].seq).toBeGreaterThan(events[i - 1].seq);
      }
    }
  }

  it('should validate strict monotonic sequence', () => {
    const events = [
      { seq: 1 }, { seq: 2 }, { seq: 3 }, { seq: 4 }, { seq: 5 },
    ];
    
    expect(() => assertMonotonicSeq(events, true)).not.toThrow();
  });

  it('should detect gaps in strict mode', () => {
    const events = [
      { seq: 1 }, { seq: 2 }, { seq: 4 }, { seq: 5 }, // Gap at 3
    ];
    
    expect(() => assertMonotonicSeq(events, true)).toThrow();
  });

  it('should allow gaps in non-strict mode', () => {
    const events = [
      { seq: 1 }, { seq: 3 }, { seq: 5 }, { seq: 10 },
    ];
    
    expect(() => assertMonotonicSeq(events, false)).not.toThrow();
  });

  it('should detect non-monotonic sequence', () => {
    const events = [
      { seq: 1 }, { seq: 2 }, { seq: 1 }, { seq: 3 }, // Decrease!
    ];
    
    expect(() => assertMonotonicSeq(events, false)).toThrow();
  });
});
