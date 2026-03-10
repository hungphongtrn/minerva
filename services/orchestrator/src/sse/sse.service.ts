/**
 * SSE Service
 *
 * High-level SSE service for orchestrator integration.
 * Wraps stream controller, event buffer, and event mapper.
 */

import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import type { SSEEventEnvelope, SSEEventType } from './types.js';
import type { SSEStream, SSEStreamController } from './stream.js';
import type { EventBuffer } from './buffer.js';
import type { EventMapper } from './mapper.js';
import { MemoryEventSequencer, DefaultEnvelopeFactory } from './envelope.js';
import { MemorySSEStreamController } from './stream.js';
import { BoundedEventBuffer } from './buffer.js';
import { DefaultEventMapper } from './mapper.js';

@Injectable()
export class SSEService implements OnModuleDestroy {
  private readonly logger = new Logger(SSEService.name);
  private sequencer: MemoryEventSequencer;
  private streamController: SSEStreamController;
  private eventBuffer: EventBuffer;
  private eventMapper: EventMapper;
  private envelopeFactory: DefaultEnvelopeFactory;

  constructor() {
    this.sequencer = new MemoryEventSequencer();
    this.streamController = new MemorySSEStreamController();
    this.eventBuffer = new BoundedEventBuffer(1000);
    this.eventMapper = new DefaultEventMapper(this.sequencer);
    this.envelopeFactory = new DefaultEnvelopeFactory(this.sequencer);
  }

  onModuleDestroy() {
    // Cleanup all connections on shutdown
    this.logger.log('Closing all SSE connections...');
  }

  /**
   * Register a new SSE connection for a run
   * @returns Cleanup function to unregister
   */
  registerStream(runId: string, stream: SSEStream): () => void {
    return this.streamController.register(runId, stream);
  }

  /**
   * Broadcast event to all connected clients for a run
   */
  broadcast(runId: string, event: SSEEventEnvelope): void {
    // Add to buffer first for replay
    this.eventBuffer.push(event);
    // Broadcast to all connected clients
    this.streamController.broadcast(runId, event);
  }

  /**
   * Map and broadcast a pi-agent-core event
   */
  broadcastAgentEvent(runId: string, agentEvent: { type: string; [key: string]: unknown }): void {
    const envelope = this.eventMapper.map(agentEvent, runId);
    if (envelope) {
      this.broadcast(runId, envelope);
    }
  }

  /**
   * Broadcast orchestrator lifecycle event
   */
  broadcastOrchestratorEvent(
    runId: string,
    type: Extract<
      SSEEventType,
      | 'run_queued'
      | 'run_started'
      | 'run_completed'
      | 'run_failed'
      | 'run_cancelled'
      | 'run_timed_out'
    >,
    payload: unknown
  ): void {
    const envelope = this.eventMapper.mapOrchestratorEvent(runId, type, payload);
    this.broadcast(runId, envelope);
  }

  /**
   * Close all connections for a run
   */
  closeRun(runId: string): void {
    this.streamController.closeRun(runId);
    this.eventBuffer.clear(runId);
    this.sequencer.cleanup(runId);
  }

  /**
   * Get buffered events from a specific sequence number
   */
  getBufferedEventsFrom(seq: number): SSEEventEnvelope[] {
    return this.eventBuffer.getFrom(seq);
  }

  /**
   * Get connection count for a run
   */
  getConnectionCount(runId: string): number {
    return this.streamController.getConnectionCount(runId);
  }

  /**
   * Get total connections across all runs
   */
  getTotalConnections(): number {
    return this.streamController.getTotalConnections();
  }

  /**
   * Get current sequence number for a run
   */
  getCurrentSeq(runId: string): number {
    return this.sequencer.current(runId);
  }

  /**
   * Create a custom envelope (for connection events)
   */
  createEnvelope<TPayload>(
    runId: string,
    type: SSEEventType,
    payload: TPayload
  ): SSEEventEnvelope<TPayload> {
    return this.envelopeFactory.create(runId, type, payload);
  }
}
