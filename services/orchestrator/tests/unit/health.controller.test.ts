import { describe, it, expect, vi } from 'vitest';
import { HealthController } from '../../src/health/health.controller.js';
import { ModelProviderService } from '../../src/model-provider/model-provider.service.js';
import type { ILogger } from '../../src/providers/types.js';

describe('HealthController', () => {
  it('returns service health details with provider info', async () => {
    const logger: ILogger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    };

    const mockModelProviderService = {
      checkHealth: vi.fn().mockResolvedValue({
        healthy: true,
        provider: 'openai',
        message: 'Provider healthy',
      }),
    } as unknown as ModelProviderService;

    const controller = new HealthController(logger, mockModelProviderService);
    const result = await controller.getHealth();

    expect(result.status).toBe('ok');
    expect(result.provider).toBeDefined();
    expect(result.provider).toMatchObject({
      type: 'openai',
      healthy: true,
    });
    expect(new Date(result.timestamp).toISOString()).toBe(result.timestamp);
    expect(logger.debug).toHaveBeenCalledWith('Health check requested');
  });

  it('returns error status when provider is unhealthy', async () => {
    const logger: ILogger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    };

    const mockModelProviderService = {
      checkHealth: vi.fn().mockResolvedValue({
        healthy: false,
        provider: 'openai',
        message: 'Invalid API key format',
        error: 'API key format validation failed',
      }),
    } as unknown as ModelProviderService;

    const controller = new HealthController(logger, mockModelProviderService);

    await expect(controller.getHealth()).rejects.toThrow();
    expect(logger.warn).toHaveBeenCalled();
  });
});
