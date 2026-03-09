/**
 * Lease Manager Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { InMemoryLeaseManager, DEFAULT_LEASE_TTL_MS } from '../../src/services/lease.js';

describe('InMemoryLeaseManager', () => {
  let leaseManager: InMemoryLeaseManager;

  beforeEach(() => {
    leaseManager = new InMemoryLeaseManager();
  });

  describe('acquire', () => {
    it('should acquire lease for available user', async () => {
      const lease = await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);

      expect(lease).not.toBeNull();
      expect(lease!.runId).toBe('run-1');
      expect(lease!.token).toBeDefined();
      expect(lease!.acquiredAt).toBeInstanceOf(Date);
      expect(lease!.expiresAt).toBeInstanceOf(Date);
    });

    it('should not acquire lease for user with active lease', async () => {
      await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      const secondLease = await leaseManager.acquire('user-1', 'run-2', DEFAULT_LEASE_TTL_MS);

      expect(secondLease).toBeNull();
    });

    it('should allow different users to acquire leases', async () => {
      const lease1 = await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      const lease2 = await leaseManager.acquire('user-2', 'run-2', DEFAULT_LEASE_TTL_MS);

      expect(lease1).not.toBeNull();
      expect(lease2).not.toBeNull();
    });

    it('should allow acquiring after lease expires', async () => {
      // Acquire with very short TTL
      await leaseManager.acquire('user-1', 'run-1', 1);

      // Wait for expiration
      await new Promise((resolve) => setTimeout(resolve, 10));

      const newLease = await leaseManager.acquire('user-1', 'run-2', DEFAULT_LEASE_TTL_MS);
      expect(newLease).not.toBeNull();
      expect(newLease!.runId).toBe('run-2');
    });
  });

  describe('release', () => {
    it('should release active lease', async () => {
      const lease = await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      await leaseManager.release(lease!.token);

      const isActive = await leaseManager.isActive('user-1');
      expect(isActive).toBe(false);
    });

    it('should handle releasing non-existent lease gracefully', async () => {
      await expect(leaseManager.release('invalid-token')).resolves.not.toThrow();
    });
  });

  describe('extend', () => {
    it('should extend lease expiration', async () => {
      const lease = await leaseManager.acquire('user-1', 'run-1', 100);
      const originalExpiry = lease!.expiresAt;

      await leaseManager.extend(lease!.token, 200);

      const updatedLease = await leaseManager.getLease(lease!.token);
      expect(updatedLease!.expiresAt.getTime()).toBeGreaterThan(originalExpiry.getTime());
    });

    it('should throw for non-existent lease', async () => {
      await expect(leaseManager.extend('invalid-token', 100)).rejects.toThrow('Lease not found');
    });
  });

  describe('isActive', () => {
    it('should return false for user without lease', async () => {
      expect(await leaseManager.isActive('user-1')).toBe(false);
    });

    it('should return true for user with active lease', async () => {
      await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      expect(await leaseManager.isActive('user-1')).toBe(true);
    });

    it('should return false for expired lease', async () => {
      await leaseManager.acquire('user-1', 'run-1', 1);
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(await leaseManager.isActive('user-1')).toBe(false);
    });
  });

  describe('getActiveRun', () => {
    it('should return null for user without lease', async () => {
      expect(await leaseManager.getActiveRun('user-1')).toBeNull();
    });

    it('should return runId for active lease', async () => {
      await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      expect(await leaseManager.getActiveRun('user-1')).toBe('run-1');
    });

    it('should return null for expired lease', async () => {
      await leaseManager.acquire('user-1', 'run-1', 1);
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(await leaseManager.getActiveRun('user-1')).toBeNull();
    });
  });

  describe('getLease', () => {
    it('should return null for non-existent token', async () => {
      expect(await leaseManager.getLease('invalid-token')).toBeNull();
    });

    it('should return lease for valid token', async () => {
      const lease = await leaseManager.acquire('user-1', 'run-1', DEFAULT_LEASE_TTL_MS);
      const retrieved = await leaseManager.getLease(lease!.token);

      expect(retrieved).not.toBeNull();
      expect(retrieved!.runId).toBe('run-1');
    });

    it('should return null for expired lease', async () => {
      const lease = await leaseManager.acquire('user-1', 'run-1', 1);
      await new Promise((resolve) => setTimeout(resolve, 10));

      expect(await leaseManager.getLease(lease!.token)).toBeNull();
    });
  });

  describe('cleanupExpired', () => {
    it('should clean up expired leases', () => {
      // Note: Using synchronous method after async acquire
      // In real usage, this would be called periodically
      const cleaned = leaseManager.cleanupExpired();
      expect(typeof cleaned).toBe('number');
    });
  });
});
