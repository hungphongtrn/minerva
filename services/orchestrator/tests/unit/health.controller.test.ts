import { Test } from '@nestjs/testing';
import { describe, expect, it, vi } from 'vitest';
import { HealthController } from '../../src/health/health.controller.js';
import { LOGGER } from '../../src/providers/provider-tokens.js';
import type { ILogger } from '../../src/providers/types.js';

describe('HealthController', () => {
  it('returns service health details', async () => {
    const logger: ILogger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    };

    const moduleRef = await Test.createTestingModule({
      controllers: [HealthController],
      providers: [{ provide: LOGGER, useValue: logger }],
    }).compile();

    const controller = moduleRef.get(HealthController);
    const result = controller.getHealth();

    expect(result.status).toBe('ok');
    expect(new Date(result.timestamp).toISOString()).toBe(result.timestamp);
    expect(logger.debug).toHaveBeenCalledWith('Health check requested');
  });
});
