/**
 * SSE Event Buffer
 *
 * Bounded event buffer for replay/resilience.
 * Keeps last N events per run for client reconnect scenarios.
 */

import type { SSEEventEnvelope } from './types.js';

export interface EventBuffer {
  /** Add event to buffer */
  push(event: SSEEventEnvelope): void;

  /** Get events from seq (inclusive) to present */
  getFrom(seq: number): SSEEventEnvelope[];

  /** Get all buffered events for a run */
  getAllForRun(runId: string): SSEEventEnvelope[];

  /** Clear buffer for a run */
  clear(runId: string): void;

  /** Get buffer size for a run */
  size(runId: string): number;
}

/**
 * Bounded event buffer for replay/resilience
 *
 * Keeps last N events per run for client reconnect scenarios.
 * Events are evicted in FIFO order when buffer is full.
 */
export class BoundedEventBuffer implements EventBuffer {
  private buffers = new Map<string, SSEEventEnvelope[]>();

  constructor(private maxSize: number = 1000) {}

  push(event: SSEEventEnvelope): void {
    let buffer = this.buffers.get(event.run_id);
    if (!buffer) {
      buffer = [];
      this.buffers.set(event.run_id, buffer);
    }

    buffer.push(event);

    // Evict oldest if over capacity
    if (buffer.length > this.maxSize) {
      buffer.shift();
    }
  }

  getFrom(seq: number): SSEEventEnvelope[] {
    // Get events from all runs with seq >= requested seq
    const result: SSEEventEnvelope[] = [];
    for (const buffer of this.buffers.values()) {
      for (const event of buffer) {
        if (event.seq >= seq) {
          result.push(event);
        }
      }
    }
    // Sort by seq to maintain order
    return result.sort((a, b) => a.seq - b.seq);
  }

  getAllForRun(runId: string): SSEEventEnvelope[] {
    const buffer = this.buffers.get(runId);
    return buffer ? [...buffer] : [];
  }

  clear(runId: string): void {
    this.buffers.delete(runId);
  }

  size(runId: string): number {
    return this.buffers.get(runId)?.length ?? 0;
  }

  /** Get total buffered events across all runs */
  getTotalSize(): number {
    let total = 0;
    for (const buffer of this.buffers.values()) {
      total += buffer.length;
    }
    return total;
  }
}
