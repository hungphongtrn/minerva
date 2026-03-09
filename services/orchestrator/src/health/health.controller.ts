import { Controller, Get, Inject } from '@nestjs/common';
import { LOGGER } from '../providers/provider-tokens.js';
import type { ILogger } from '../providers/types.js';

@Controller('health')
export class HealthController {
  constructor(@Inject(LOGGER) private readonly logger: ILogger) {}

  @Get()
  getHealth(): { status: string; timestamp: string } {
    this.logger.debug('Health check requested');

    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
    };
  }
}
