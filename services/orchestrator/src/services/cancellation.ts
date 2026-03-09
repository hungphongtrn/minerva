/**
 * Cancellation Context and Registry
 * 
 * Manages AbortController instances for run cancellation.
 * Provides signal propagation through the entire execution stack.
 */

export interface CancellationContext {
  /** The run this context is for */
  runId: string;
  
  /** AbortController for this run */
  controller: AbortController;
  
  /** AbortSignal for cancellation propagation */
  signal: AbortSignal;
  
  /** Whether this run has been cancelled */
  isCancelled: boolean;
  
  /** Cancel reason/message */
  cancelReason?: string;
  
  /**
   * Cancel this run
   * @param reason - Optional reason for cancellation
   */
  cancel(reason?: string): void;
}

export interface CancellationRegistry {
  /**
   * Create a new cancellation context for a run
   */
  create(runId: string): CancellationContext;
  
  /**
   * Get an existing cancellation context
   */
  get(runId: string): CancellationContext | undefined;
  
  /**
   * Remove a cancellation context (cleanup after run completes)
   */
  remove(runId: string): void;
  
  /**
   * Cancel a specific run
   * @returns true if run was found and cancelled, false otherwise
   */
  cancel(runId: string, reason?: string): boolean;
  
  /**
   * Cancel all active runs
   */
  cancelAll(reason?: string): void;
  
  /**
   * Check if a run has been cancelled
   */
  isCancelled(runId: string): boolean;
  
  /**
   * Get all active run IDs
   */
  getActiveRunIds(): string[];
}

/**
 * Implementation of CancellationContext
 */
class CancellationContextImpl implements CancellationContext {
  runId: string;
  controller: AbortController;
  signal: AbortSignal;
  isCancelled: boolean = false;
  cancelReason?: string;
  
  constructor(runId: string) {
    this.runId = runId;
    this.controller = new AbortController();
    this.signal = this.controller.signal;
  }
  
  cancel(reason?: string): void {
    if (this.isCancelled) {
      return;
    }
    
    this.isCancelled = true;
    this.cancelReason = reason ?? 'cancelled';
    this.controller.abort(this.cancelReason);
  }
}

/**
 * In-memory cancellation registry
 */
export class InMemoryCancellationRegistry implements CancellationRegistry {
  private contexts: Map<string, CancellationContextImpl> = new Map();

  create(runId: string): CancellationContext {
    // Remove any existing context for this run
    this.remove(runId);
    
    const context = new CancellationContextImpl(runId);
    this.contexts.set(runId, context);
    
    return context;
  }

  get(runId: string): CancellationContext | undefined {
    return this.contexts.get(runId);
  }

  remove(runId: string): void {
    this.contexts.delete(runId);
  }

  cancel(runId: string, reason?: string): boolean {
    const context = this.contexts.get(runId);
    if (!context) {
      return false;
    }
    
    context.cancel(reason);
    return true;
  }

  cancelAll(reason?: string): void {
    for (const context of this.contexts.values()) {
      context.cancel(reason);
    }
  }

  isCancelled(runId: string): boolean {
    return this.contexts.get(runId)?.isCancelled ?? false;
  }

  getActiveRunIds(): string[] {
    return Array.from(this.contexts.keys());
  }
  
  /**
   * Clear all contexts (useful for testing)
   */
  clear(): void {
    this.contexts.clear();
  }
}

/**
 * Singleton cancellation registry instance
 */
export const cancellationRegistry: CancellationRegistry = new InMemoryCancellationRegistry();
