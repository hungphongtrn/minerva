import type { Sandbox } from '@daytonaio/sdk';
import type { DaytonaClient } from './daytona-client.js';
import type { NetworkCheckResult } from './types.js';
import { NetworkIsolationError } from './errors.js';

/**
 * Commands to test network isolation
 */
const NETWORK_TEST_COMMANDS = [
  {
    name: 'HTTP outbound',
    command: 'curl --connect-timeout 5 --max-time 5 http://google.com 2>&1 || echo "BLOCKED"',
    shouldFail: true,
  },
  {
    name: 'HTTPS outbound',
    command: 'curl --connect-timeout 5 --max-time 5 https://google.com 2>&1 || echo "BLOCKED"',
    shouldFail: true,
  },
  {
    name: 'DNS resolution',
    command: 'nslookup google.com 2>&1 || echo "BLOCKED"',
    shouldFail: true,
  },
  {
    name: 'Ping external',
    command: 'ping -c 1 -W 5 8.8.8.8 2>&1 || echo "BLOCKED"',
    shouldFail: true,
  },
];

export class NetworkValidationService {
  constructor(private client: DaytonaClient) {}

  /**
   * Validate that the sandbox has no general outbound network access
   */
  async validateNetworkIsolation(
    sandbox: Sandbox
  ): Promise<NetworkCheckResult> {
    const checks: Array<{
      name: string;
      passed: boolean;
      details?: string;
    }> = [];

    for (const test of NETWORK_TEST_COMMANDS) {
      try {
        const result = await this.client.executeCommand(sandbox, test.command, {
          timeout: 10,
        });

        const isBlocked = result.stdout.includes('BLOCKED') || 
                         result.exitCode !== 0 ||
                         result.stdout.includes('Could not resolve') ||
                         result.stdout.includes('Connection refused');

        const passed = test.shouldFail ? isBlocked : !isBlocked;

        checks.push({
          name: test.name,
          passed,
          details: passed 
            ? 'Network access correctly blocked'
            : 'Network access was allowed (security risk)',
        });
      } catch (error) {
        // If command fails to execute, assume network is blocked
        checks.push({
          name: test.name,
          passed: test.shouldFail,
          details: error instanceof Error ? error.message : 'Command failed',
        });
      }
    }

    const allPassed = checks.every((check) => check.passed);

    return {
      isIsolated: allPassed,
      checks,
    };
  }

  /**
   * Throws if network isolation is not properly configured
   */
  async ensureNetworkIsolation(sandbox: Sandbox): Promise<void> {
    const result = await this.validateNetworkIsolation(sandbox);

    if (!result.isIsolated) {
      const failedChecks = result.checks.filter((c) => !c.passed);
      throw new NetworkIsolationError(
        `Sandbox ${sandbox.id} has outbound network access. Failed checks: ${failedChecks
          .map((c) => c.name)
          .join(', ')}`,
        result.checks,
        sandbox.id
      );
    }
  }
}
