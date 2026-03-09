/**
 * Lease Service
 * 
 * Manages distributed leases to ensure only one active run per user.
 * Provides TTL-based leases for crash recovery.
 */

export interface Lease {
  /** The run that acquired this lease */
  runId: string;
  
  /** Unique token for this lease instance */
  token: string;
  
  /** When the lease was acquired */
  acquiredAt: Date;
  
  /** When the lease expires */
  expiresAt: Date;
}

export interface LeaseManager {
  /**
   * Attempt to acquire a lease for a run
   * @param userId - The user to acquire lease for
   * @param runId - The run attempting to acquire
   * @param ttlMs - Time-to-live in milliseconds
   * @returns The lease if acquired, null if another run already has an active lease
   */
  acquire(userId: string, runId: string, ttlMs: number): Promise<Lease | null>;
  
  /**
   * Release a lease
   */
  release(leaseToken: string): Promise<void>;
  
  /**
   * Extend an existing lease
   */
  extend(leaseToken: string, additionalMs: number): Promise<void>;
  
  /**
   * Check if a user has an active lease
   */
  isActive(userId: string): Promise<boolean>;
  
  /**
   * Get the active run ID for a user
   * @returns The runId or null if no active lease
   */
  getActiveRun(userId: string): Promise<string | null>;
  
  /**
   * Get lease by token
   */
  getLease(leaseToken: string): Promise<Lease | null>;
}

/**
 * In-memory lease manager implementation
 */
export class InMemoryLeaseManager implements LeaseManager {
  // Map of userId -> active lease
  private leases: Map<string, Lease> = new Map();
  
  // Map of leaseToken -> userId for quick lookups
  private tokenToUser: Map<string, string> = new Map();

  acquire(userId: string, runId: string, ttlMs: number): Promise<Lease | null> {
    // Check if there's already an active lease for this user
    const existingLease = this.leases.get(userId);
    if (existingLease) {
      // Check if lease has expired
      if (existingLease.expiresAt > new Date()) {
        // Active lease exists, cannot acquire
        return Promise.resolve(null);
      }
      // Lease expired, clean it up
      this.tokenToUser.delete(existingLease.token);
    }
    
    // Generate lease token (using timestamp + random for v0)
    const token = `lease_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    const now = new Date();
    const lease: Lease = {
      runId,
      token,
      acquiredAt: now,
      expiresAt: new Date(now.getTime() + ttlMs),
    };
    
    this.leases.set(userId, lease);
    this.tokenToUser.set(token, userId);
    
    return Promise.resolve(lease);
  }

  release(leaseToken: string): Promise<void> {
    const userId = this.tokenToUser.get(leaseToken);
    if (!userId) {
      return Promise.resolve();
    }
    
    const lease = this.leases.get(userId);
    if (lease?.token === leaseToken) {
      this.leases.delete(userId);
      this.tokenToUser.delete(leaseToken);
    }

    return Promise.resolve();
  }

  extend(leaseToken: string, additionalMs: number): Promise<void> {
    const userId = this.tokenToUser.get(leaseToken);
    if (!userId) {
      return Promise.reject(new Error('Lease not found'));
    }
    
    const lease = this.leases.get(userId);
    if (!lease || lease.token !== leaseToken) {
      return Promise.reject(new Error('Lease not found'));
    }
    
    // Extend expiration
    lease.expiresAt = new Date(lease.expiresAt.getTime() + additionalMs);
    return Promise.resolve();
  }

  isActive(userId: string): Promise<boolean> {
    const lease = this.leases.get(userId);
    if (!lease) {
      return Promise.resolve(false);
    }
    
    // Check if expired
    if (lease.expiresAt <= new Date()) {
      // Clean up expired lease
      this.tokenToUser.delete(lease.token);
      this.leases.delete(userId);
      return Promise.resolve(false);
    }
    
    return Promise.resolve(true);
  }

  async getActiveRun(userId: string): Promise<string | null> {
    const isActive = await this.isActive(userId);
    if (!isActive) {
      return null;
    }
    
    return this.leases.get(userId)?.runId ?? null;
  }

  getLease(leaseToken: string): Promise<Lease | null> {
    const userId = this.tokenToUser.get(leaseToken);
    if (!userId) {
      return Promise.resolve(null);
    }
    
    const lease = this.leases.get(userId);
    if (!lease || lease.token !== leaseToken) {
      return Promise.resolve(null);
    }
    
    // Check if expired
    if (lease.expiresAt <= new Date()) {
      return Promise.resolve(null);
    }
    
    return Promise.resolve(lease);
  }
  
  /**
   * Clean up all expired leases
   * @returns Number of leases cleaned up
   */
  cleanupExpired(): number {
    const now = new Date();
    let cleaned = 0;
    
    for (const [userId, lease] of this.leases.entries()) {
      if (lease.expiresAt <= now) {
        this.tokenToUser.delete(lease.token);
        this.leases.delete(userId);
        cleaned++;
      }
    }
    
    return cleaned;
  }
  
  /**
   * Clear all leases (useful for testing)
   */
  clear(): void {
    this.leases.clear();
    this.tokenToUser.clear();
  }
}

/**
 * Default lease TTL: 30 seconds for acquisition, extendable during execution
 */
export const DEFAULT_LEASE_TTL_MS = 30_000;

/**
 * Singleton lease manager instance
 */
export const leaseManager: LeaseManager = new InMemoryLeaseManager();
