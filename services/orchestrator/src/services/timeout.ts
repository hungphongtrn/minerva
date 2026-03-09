/**
 * Timeout Service
 * 
 * Schedules and enforces run timeouts.
 * Uses setTimeout for scheduling with cleanup on completion.
 */



export interface TimeoutHandle {
  /** The run this timeout is for */
  runId: string;
  
  /** When the timeout is scheduled to fire */
  scheduledAt: Date;
  
  /** When the timeout will fire */
  timeoutAt: Date;
  
  /** Clear this timeout */
  clear(): void;
}

export interface TimeoutManager {
  /**
   * Schedule a timeout for a run
   * @param runId - The run to timeout
   * @param delayMs - Milliseconds until timeout
   * @param onTimeout - Callback when timeout fires
   * @returns Timeout handle for cancellation
   */
  schedule(
    runId: string,
    delayMs: number,
    onTimeout: (runId: string) => void | Promise<void>
  ): TimeoutHandle;
  
  /**
   * Clear a scheduled timeout
   */
  clear(runId: string): boolean;
  
  /**
   * Check if a run has a scheduled timeout
   */
  has(runId: string): boolean;
  
  /**
   * Get scheduled timeout time for a run
   * @returns The timeout timestamp or null if not scheduled
   */
  getTimeoutAt(runId: string): Date | null;
  
  /**
   * Clear all timeouts (useful for shutdown)
   */
  clearAll(): void;
}

/**
 * Internal timeout handle implementation
 */
class TimeoutHandleImpl implements TimeoutHandle {
  runId: string;
  scheduledAt: Date;
  timeoutAt: Date;
  private timer: ReturnType<typeof setTimeout>;
  private onTimeout: () => void;
  
  constructor(
    runId: string,
    delayMs: number,
    onTimeout: () => void
  ) {
    this.runId = runId;
    this.scheduledAt = new Date();
    this.timeoutAt = new Date(Date.now() + delayMs);
    this.onTimeout = onTimeout;
    
    this.timer = setTimeout(() => {
      this.onTimeout();
    }, delayMs);
  }
  
  clear(): void {
    clearTimeout(this.timer);
  }
}

/**
 * In-memory timeout manager
 */
export class InMemoryTimeoutManager implements TimeoutManager {
  private timeouts: Map<string, TimeoutHandleImpl> = new Map();

  schedule(
    runId: string,
    delayMs: number,
    onTimeout: (runId: string) => void | Promise<void>
  ): TimeoutHandle {
    // Clear any existing timeout for this run
    this.clear(runId);
    
    const handle = new TimeoutHandleImpl(
      runId,
      delayMs,
      () => {
        this.timeouts.delete(runId);
        void onTimeout(runId);
      }
    );
    
    this.timeouts.set(runId, handle);
    return handle;
  }

  clear(runId: string): boolean {
    const handle = this.timeouts.get(runId);
    if (!handle) {
      return false;
    }
    
    handle.clear();
    this.timeouts.delete(runId);
    return true;
  }

  has(runId: string): boolean {
    return this.timeouts.has(runId);
  }

  getTimeoutAt(runId: string): Date | null {
    return this.timeouts.get(runId)?.timeoutAt ?? null;
  }

  clearAll(): void {
    for (const handle of this.timeouts.values()) {
      handle.clear();
    }
    this.timeouts.clear();
  }
  
  /**
   * Get all scheduled run IDs
   */
  getScheduledRunIds(): string[] {
    return Array.from(this.timeouts.keys());
  }
}

/**
 * Singleton timeout manager instance
 */
export const timeoutManager: TimeoutManager = new InMemoryTimeoutManager();

/**
 * Default run timeout: 10 minutes
 */
export const DEFAULT_RUN_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Maximum run timeout: 1 hour
 */
export const MAX_RUN_TIMEOUT_MS = 60 * 60 * 1000;
