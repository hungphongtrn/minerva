import { Controller, Get, Inject, ServiceUnavailableException } from '@nestjs/common';
import { LOGGER } from '../providers/provider-tokens.js';
import type { ILogger } from '../providers/types.js';
import { ModelProviderService } from '../model-provider/model-provider.service.js';

@Controller('health')
export class HealthController {
  constructor(
    @Inject(LOGGER) private readonly logger: ILogger,
    private readonly modelProviderService: ModelProviderService
  ) {}

  @Get()
  async getHealth(): Promise<{ status: string; timestamp: string; provider?: unknown }> {
    this.logger.debug('Health check requested');

    // Check model provider health
    const providerHealth = await this.modelProviderService.checkHealth();

    const response: { status: string; timestamp: string; provider?: unknown } = {
      status: providerHealth.healthy ? 'ok' : 'error',
      timestamp: new Date().toISOString(),
      provider: {
        type: providerHealth.provider,
        healthy: providerHealth.healthy,
        message: providerHealth.message,
      },
    };

    if (!providerHealth.healthy) {
      this.logger.warn('Health check failed - provider unhealthy', {
        provider: providerHealth.provider,
        error: providerHealth.error,
      });
      throw new ServiceUnavailableException(response);
    }

    return response;
  }
}
