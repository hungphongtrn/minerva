import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { ORCHESTRATOR_CONFIG } from './config/config.constants.js';
import type { OrchestratorConfig } from './config/types.js';
import { LOGGER } from './providers/provider-tokens.js';
import type { ILogger } from './providers/types.js';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule, { logger: false });
  app.enableShutdownHooks();

  const config = app.get<OrchestratorConfig>(ORCHESTRATOR_CONFIG);
  const logger = app.get<ILogger>(LOGGER);

  logger.info('Starting orchestrator service', { nodeEnv: process.env.NODE_ENV });

  await app.listen(config.server.port, config.server.host);

  logger.info(`Server running at http://${config.server.host}:${config.server.port}`);
}

bootstrap().catch((error: unknown) => {
  console.error('Fatal error starting server:', error);
  process.exit(1);
});
