import { Global, Module } from '@nestjs/common';
import { ORCHESTRATOR_CONFIG } from '../config/config.constants.js';
import type { OrchestratorConfig } from '../config/types.js';
import { createLogger } from './logger.js';
import { LOGGER } from './provider-tokens.js';
import type { ILogger } from './types.js';

@Global()
@Module({
  providers: [
    {
      provide: LOGGER,
      inject: [ORCHESTRATOR_CONFIG],
      useFactory: (config: OrchestratorConfig): ILogger => createLogger(config.logging.level),
    },
  ],
  exports: [LOGGER],
})
export class LoggerModule {}
