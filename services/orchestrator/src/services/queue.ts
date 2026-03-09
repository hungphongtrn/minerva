/**
 * Run Queue Service
 * 
 * Provides per-user FIFO queueing to ensure one active run per user.
 * In-memory implementation for v0, can be swapped for Redis later.
 */



export interface RunQueue {
  /**
   * Add a run to the user's queue
   * @returns The position in queue (0 = next to run)
   */
  enqueue(runId: string, userId: string): Promise<number>;
  
  /**
   * Remove and return the next run from the user's queue
   * @returns The runId or null if queue is empty
   */
  dequeue(userId: string): Promise<string | null>;
  
  /**
   * View the next run without removing it
   * @returns The runId or null if queue is empty
   */
  peek(userId: string): Promise<string | null>;
  
  /**
   * Remove a specific run from the queue
   * @returns true if found and removed, false otherwise
   */
  remove(runId: string): Promise<boolean>;
  
  /**
   * Get the position of a run in the queue
   * @returns Position (0-indexed) or null if not in queue
   */
  getPosition(runId: string): Promise<number | null>;
  
  /**
   * Get the length of a user's queue
   */
  getLength(userId: string): Promise<number>;
  
  /**
   * Clear all queues (useful for testing)
   */
  clear(): Promise<void>;
}

/**
 * In-memory implementation of the run queue
 */
export class InMemoryRunQueue implements RunQueue {
  // Map of userId -> array of runIds (FIFO)
  private queues: Map<string, string[]> = new Map();
  
  // Map of runId -> userId for quick lookups
  private runToUser: Map<string, string> = new Map();

  enqueue(runId: string, userId: string): Promise<number> {
    // Get or create queue for this user
    let queue = this.queues.get(userId);
    if (!queue) {
      queue = [];
      this.queues.set(userId, queue);
    }
    
    // Add run to queue
    queue.push(runId);
    this.runToUser.set(runId, userId);
    
    // Return position (0-indexed)
    return Promise.resolve(queue.length - 1);
  }

  dequeue(userId: string): Promise<string | null> {
    const queue = this.queues.get(userId);
    if (!queue || queue.length === 0) {
      return Promise.resolve(null);
    }
    
    // Remove and return first element (FIFO)
    const runId = queue.shift()!;
    this.runToUser.delete(runId);
    
    // Clean up empty queues
    if (queue.length === 0) {
      this.queues.delete(userId);
    }
    
    return Promise.resolve(runId);
  }

  peek(userId: string): Promise<string | null> {
    const queue = this.queues.get(userId);
    if (!queue || queue.length === 0) {
      return Promise.resolve(null);
    }
    
    return Promise.resolve(queue[0]);
  }

  remove(runId: string): Promise<boolean> {
    const userId = this.runToUser.get(runId);
    if (!userId) {
      return Promise.resolve(false);
    }
    
    const queue = this.queues.get(userId);
    if (!queue) {
      return Promise.resolve(false);
    }
    
    const index = queue.indexOf(runId);
    if (index === -1) {
      return Promise.resolve(false);
    }
    
    // Remove from queue
    queue.splice(index, 1);
    this.runToUser.delete(runId);
    
    // Clean up empty queues
    if (queue.length === 0) {
      this.queues.delete(userId);
    }
    
    return Promise.resolve(true);
  }

  getPosition(runId: string): Promise<number | null> {
    const userId = this.runToUser.get(runId);
    if (!userId) {
      return Promise.resolve(null);
    }
    
    const queue = this.queues.get(userId);
    if (!queue) {
      return Promise.resolve(null);
    }
    
    const index = queue.indexOf(runId);
    return Promise.resolve(index === -1 ? null : index);
  }

  getLength(userId: string): Promise<number> {
    const queue = this.queues.get(userId);
    return Promise.resolve(queue?.length ?? 0);
  }

  clear(): Promise<void> {
    this.queues.clear();
    this.runToUser.clear();
    return Promise.resolve();
  }
  
  /**
   * Get all runIds for a user (useful for testing/debugging)
   */
  getUserRuns(userId: string): string[] {
    return [...(this.queues.get(userId) ?? [])];
  }
}

/**
 * Singleton queue instance
 */
export const runQueue: RunQueue = new InMemoryRunQueue();
