/**
 * SSE Event Envelope
 *
 * Event sequencing, timestamp generation, and envelope factory.
 */

import type { SSEEventEnvelope, SSEEventType } from './types.js';

export interface EventSequencer {
  /** Get next sequence number for a run */
  next(runId: string): number;

  /** Get current sequence number for a run */
  current(runId: string): number;

  /** Reset sequence for a run (on reconnect/resume) */
  reset(runId: string, startAt?: number): void;
}

export interface EnvelopeFactory {
  /** Create an envelope with auto-incrementing seq */
  create<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload
  ): SSEEventEnvelope<TPayload>;

  /** Create envelope at specific seq (for replay) */
  createAt<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload,
    seq: number,
    ts: string
  ): SSEEventEnvelope<TPayload>;
}

/** In-memory sequencer implementation (v0) */
export class MemoryEventSequencer implements EventSequencer {
  private counters = new Map<string, number>();

  next(runId: string): number {
    const current = this.counters.get(runId) ?? 0;
    const next = current + 1;
    this.counters.set(runId, next);
    return next;
  }

  current(runId: string): number {
    return this.counters.get(runId) ?? 0;
  }

  reset(runId: string, startAt = 0): void {
    this.counters.set(runId, startAt);
  }

  /** Cleanup when run ends */
  cleanup(runId: string): void {
    this.counters.delete(runId);
  }
}

/**
 * Default envelope factory implementation
 *
 * Creates SSE event envelopes with auto-generated timestamps
 * and sequence numbers.
 */
export class DefaultEnvelopeFactory implements EnvelopeFactory {
  constructor(private sequencer: EventSequencer) {}

  create<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload
  ): SSEEventEnvelope<TPayload> {
    return {
      type,
      run_id: runId,
      ts: new Date().toISOString(),
      seq: this.sequencer.next(runId),
      payload,
    };
  }

  createAt<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload,
    seq: number,
    ts: string
  ): SSEEventEnvelope<TPayload> {
    return {
      type,
      run_id: runId,
      ts,
      seq,
      payload,
    };
  }
}
