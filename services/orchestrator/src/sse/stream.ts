/**
 * SSE Stream Controller
 *
 * Manages SSE connections, broadcasting events, and cleanup.
 */

import type { SSEEventEnvelope } from './types.js';

export interface SSEStream {
  /** Write event to stream */
  write(event: SSEEventEnvelope): void;

  /** Close stream gracefully */
  close(): void;

  /** Check if stream is still open */
  isOpen(): boolean;

  /** Get client IP for logging */
  getClientInfo(): { ip: string; userAgent?: string };
}

export interface SSEStreamController {
  /** Register a new SSE connection for a run */
  register(runId: string, stream: SSEStream): () => void;

  /** Broadcast event to all connected clients for a run */
  broadcast(runId: string, event: SSEEventEnvelope): void;

  /** Close all connections for a run */
  closeRun(runId: string): void;

  /** Get connection count for a run */
  getConnectionCount(runId: string): number;

  /** Get total connections across all runs */
  getTotalConnections(): number;
}

/**
 * In-memory stream controller (v0)
 *
 * Maintains mapping of runId -> Set of active streams
 * Handles cleanup on disconnect and run completion.
 */
export class MemorySSEStreamController implements SSEStreamController {
  private streams = new Map<string, Set<SSEStream>>();

  register(runId: string, stream: SSEStream): () => void {
    if (!this.streams.has(runId)) {
      this.streams.set(runId, new Set());
    }

    const runStreams = this.streams.get(runId)!;
    runStreams.add(stream);

    // Return cleanup function
    return () => {
      runStreams.delete(stream);
      if (runStreams.size === 0) {
        this.streams.delete(runId);
      }

      // Close stream if still open
      if (stream.isOpen()) {
        try {
          stream.close();
        } catch {
          // Ignore close errors
        }
      }
    };
  }

  broadcast(runId: string, event: SSEEventEnvelope): void {
    const runStreams = this.streams.get(runId);
    if (!runStreams) return;

    const deadStreams: SSEStream[] = [];

    for (const stream of runStreams) {
      try {
        if (stream.isOpen()) {
          stream.write(event);
        } else {
          deadStreams.push(stream);
        }
      } catch (err) {
        // Stream error - mark for cleanup
        deadStreams.push(stream);
      }
    }

    // Cleanup dead streams
    for (const dead of deadStreams) {
      runStreams.delete(dead);
      try {
        dead.close();
      } catch {
        // Ignore close errors
      }
    }

    if (runStreams.size === 0) {
      this.streams.delete(runId);
    }
  }

  closeRun(runId: string): void {
    const runStreams = this.streams.get(runId);
    if (!runStreams) return;

    for (const stream of runStreams) {
      try {
        stream.close();
      } catch {
        // Ignore close errors
      }
    }

    this.streams.delete(runId);
  }

  getConnectionCount(runId: string): number {
    return this.streams.get(runId)?.size ?? 0;
  }

  getTotalConnections(): number {
    let total = 0;
    for (const runStreams of this.streams.values()) {
      total += runStreams.size;
    }
    return total;
  }
}
