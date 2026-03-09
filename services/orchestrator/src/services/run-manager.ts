/**
 * Run Manager
 * 
 * High-level run lifecycle management.
 * Coordinates queue, lease, cancellation, and timeout services.
 */

import {
  Run,
  RunState,
  RunMetadata,
  AgentMessage,
  CreateRunInput,
  isValidStateTransition,
  isTerminalState,
} from '../types/run.js';

import {
  RunNotFoundError,
  InvalidStateTransitionError,
} from '../types/errors.js';
import { RunQueue, runQueue } from './queue.js';
import { LeaseManager, leaseManager as defaultLeaseManager, DEFAULT_LEASE_TTL_MS } from './lease.js';
import {
  CancellationRegistry,
  cancellationRegistry as defaultCancellationRegistry,
} from './cancellation.js';
import {
  TimeoutManager,
  timeoutManager as defaultTimeoutManager,
  DEFAULT_RUN_TIMEOUT_MS,
  MAX_RUN_TIMEOUT_MS,
} from './timeout.js';

/**
 * Repository interface for run persistence
 */
export interface RunRepository {
  create(run: Run): Promise<void>;
  getById(runId: string): Promise<Run | null>;
  getByUserId(userId: string): Promise<Run[]>;
  update(runId: string, updates: Partial<Run>): Promise<void>;
  delete(runId: string): Promise<void>;
}

/**
 * In-memory run repository for v0
 */
export class InMemoryRunRepository implements RunRepository {
  private runs: Map<string, Run> = new Map();

  create(run: Run): Promise<void> {
    this.runs.set(run.id, { ...run });
    return Promise.resolve();
  }

  getById(runId: string): Promise<Run | null> {
    const run = this.runs.get(runId);
    return Promise.resolve(run ? { ...run } : null);
  }

  getByUserId(userId: string): Promise<Run[]> {
    return Promise.resolve(Array.from(this.runs.values())
      .filter((run) => run.userId === userId)
      .map((run) => ({ ...run })));
  }

  update(runId: string, updates: Partial<Run>): Promise<void> {
    const run = this.runs.get(runId);
    if (!run) {
      return Promise.reject(new RunNotFoundError(runId));
    }
    
    Object.assign(run, updates);
    return Promise.resolve();
  }

  delete(runId: string): Promise<void> {
    this.runs.delete(runId);
    return Promise.resolve();
  }
  
  clear(): void {
    this.runs.clear();
  }
}

/**
 * Run manager configuration
 */
export interface RunManagerConfig {
  defaultTimeoutMs: number;
  maxTimeoutMs: number;
  leaseTtlMs: number;
}

/**
 * Run manager handles the complete run lifecycle
 */
export class RunManager {
  private repo: RunRepository;
  private queue: RunQueue;
  private leaseManager: LeaseManager;
  private cancellationRegistry: CancellationRegistry;
  private timeoutManager: TimeoutManager;
  private config: RunManagerConfig;

  constructor(
    repo: RunRepository = new InMemoryRunRepository(),
    queue: RunQueue = runQueue,
    leaseManager: LeaseManager = defaultLeaseManager,
    cancellationRegistry: CancellationRegistry = defaultCancellationRegistry,
    timeoutManager: TimeoutManager = defaultTimeoutManager,
    config: Partial<RunManagerConfig> = {}
  ) {
    this.repo = repo;
    this.queue = queue;
    this.leaseManager = leaseManager;
    this.cancellationRegistry = cancellationRegistry;
    this.timeoutManager = timeoutManager;
    this.config = {
      defaultTimeoutMs: config.defaultTimeoutMs ?? DEFAULT_RUN_TIMEOUT_MS,
      maxTimeoutMs: config.maxTimeoutMs ?? MAX_RUN_TIMEOUT_MS,
      leaseTtlMs: config.leaseTtlMs ?? DEFAULT_LEASE_TTL_MS,
    };
  }

  /**
   * Create a new run and add it to the queue
   */
  async createRun(input: CreateRunInput): Promise<Run> {
    const now = new Date();
    const maxDurationMs = Math.min(
      input.maxDurationMs ?? this.config.defaultTimeoutMs,
      this.config.maxTimeoutMs
    );
    
    // Generate ULID-like ID (timestamp + random)
    const runId = `run_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    
    const run: Run = {
      id: runId,
      userId: input.userId,
      state: RunState.QUEUED,
      createdAt: now,
      maxDurationMs,
      agentPackId: input.agentPackId,
      prompt: input.prompt,
    };
    
    // Persist run
    await this.repo.create(run);
    
    // Add to queue
    const position = await this.queue.enqueue(runId, input.userId);
    run.queuePosition = position;
    
    // Update with queue position
    await this.repo.update(runId, { queuePosition: position });
    
    return run;
  }

  /**
   * Get a run by ID
   */
  async getRun(runId: string): Promise<Run | null> {
    return this.repo.getById(runId);
  }

  /**
   * Get all runs for a user
   */
  async getUserRuns(userId: string): Promise<Run[]> {
    return this.repo.getByUserId(userId);
  }

  /**
   * Transition a run to a new state
   */
  async transitionState(
    runId: string,
    newState: RunState,
    metadata?: { error?: string; finalMessages?: unknown[] }
  ): Promise<Run> {
    const run = await this.repo.getById(runId);
    if (!run) {
      throw new RunNotFoundError(runId);
    }
    
    // Validate state transition
    if (!isValidStateTransition(run.state, newState)) {
      throw new InvalidStateTransitionError(runId, run.state, newState);
    }
    
    const updates: Partial<Run> = {
      state: newState,
    };
    
    // Set timestamps based on state
    if (newState === RunState.RUNNING && !run.startedAt) {
      updates.startedAt = new Date();
    }
    
    if (isTerminalState(newState)) {
      updates.completedAt = new Date();
      updates.queuePosition = undefined;
      
      // Clear timeout if set
      this.timeoutManager.clear(runId);
    }
    
    // Add metadata
    if (metadata?.error) {
      updates.error = metadata.error;
    }
    
    if (metadata?.finalMessages) {
      updates.finalMessages = metadata.finalMessages as AgentMessage[];
    }
    
    await this.repo.update(runId, updates);
    
    // Return updated run
    return (await this.repo.getById(runId))!;
  }

  /**
   * Acquire a lease for the next queued run for a user
   * @returns The run if lease acquired, null if no runs or lease unavailable
   */
  async acquireNextRun(userId: string): Promise<Run | null> {
    // Peek at next run in queue
    const nextRunId = await this.queue.peek(userId);
    if (!nextRunId) {
      return null;
    }
    
    // Try to acquire lease
    const lease = await this.leaseManager.acquire(
      userId,
      nextRunId,
      this.config.leaseTtlMs
    );
    
    if (!lease) {
      return null;
    }
    
    // Dequeue the run
    await this.queue.dequeue(userId);
    
    // Update run with lease info and transition state
    const now = new Date();
    await this.repo.update(nextRunId, {
      state: RunState.LEASED,
      leaseToken: lease.token,
      leaseExpiresAt: lease.expiresAt,
      queuePosition: undefined,
      startedAt: now,
    });
    
    return this.repo.getById(nextRunId);
  }

  /**
   * Start executing a leased run
   */
  async startRun(runId: string): Promise<Run> {
    const run = await this.transitionState(runId, RunState.RUNNING);
    
    // Create cancellation context
    this.cancellationRegistry.create(runId);
    
    // Schedule timeout
    this.timeoutManager.schedule(
      runId,
      run.maxDurationMs,
      async (timedOutRunId) => {
        await this.timeoutRun(timedOutRunId);
      }
    );
    
    return run;
  }

  /**
   * Cancel a run
   */
  async cancelRun(runId: string, reason?: string): Promise<Run> {
    const run = await this.repo.getById(runId);
    if (!run) {
      throw new RunNotFoundError(runId);
    }
    
    // If already in terminal state, nothing to do
    if (isTerminalState(run.state)) {
      return run;
    }
    
    // Remove from queue if still queued
    if (run.state === RunState.QUEUED) {
      await this.queue.remove(runId);
    }
    
    // Release lease if active
    if (run.leaseToken) {
      await this.leaseManager.release(run.leaseToken);
    }
    
    // Signal cancellation
    this.cancellationRegistry.cancel(runId, reason ?? 'user_cancelled');
    
    // Transition state
    return this.transitionState(runId, RunState.CANCELLED, {
      error: reason ?? 'cancelled',
    });
  }

  /**
   * Handle run timeout
   */
  private async timeoutRun(runId: string): Promise<void> {
    const run = await this.repo.getById(runId);
    if (!run || isTerminalState(run.state)) {
      return;
    }
    
    // Release lease
    if (run.leaseToken) {
      await this.leaseManager.release(run.leaseToken);
    }
    
    // Signal cancellation with timeout reason
    this.cancellationRegistry.cancel(runId, 'timeout');
    
    // Transition state
    await this.transitionState(runId, RunState.TIMED_OUT, {
      error: `Run exceeded maximum duration of ${run.maxDurationMs}ms`,
    });
  }

  /**
   * Complete a run successfully
   */
  async completeRun(
    runId: string,
    finalMessages?: unknown[]
  ): Promise<Run> {
    const run = await this.repo.getById(runId);
    if (!run) {
      throw new RunNotFoundError(runId);
    }
    
    // Release lease
    if (run.leaseToken) {
      await this.leaseManager.release(run.leaseToken);
    }
    
    // Clean up cancellation context
    this.cancellationRegistry.remove(runId);
    
    return this.transitionState(runId, RunState.COMPLETED, { finalMessages });
  }

  /**
   * Fail a run
   */
  async failRun(runId: string, error: Error | string): Promise<Run> {
    const run = await this.repo.getById(runId);
    if (!run) {
      throw new RunNotFoundError(runId);
    }
    
    // Release lease
    if (run.leaseToken) {
      await this.leaseManager.release(run.leaseToken);
    }
    
    // Clean up cancellation context
    this.cancellationRegistry.remove(runId);
    
    const errorMessage = error instanceof Error ? error.message : String(error);
    return this.transitionState(runId, RunState.FAILED, { error: errorMessage });
  }

  /**
   * Get cancellation signal for a run
   */
  getCancellationSignal(runId: string): AbortSignal | undefined {
    return this.cancellationRegistry.get(runId)?.signal;
  }

  /**
   * Check if a run has been cancelled
   */
  isCancelled(runId: string): boolean {
    return this.cancellationRegistry.isCancelled(runId);
  }

  /**
   * Convert run to metadata
   */
  toMetadata(run: Run): RunMetadata {
    return {
      runId: run.id,
      state: run.state,
      createdAt: run.createdAt.toISOString(),
      startedAt: run.startedAt?.toISOString(),
      completedAt: run.completedAt?.toISOString(),
      queuePosition: run.queuePosition,
      error: run.error,
    };
  }
}

/**
 * Singleton run manager instance
 */
export const runManager = new RunManager();
