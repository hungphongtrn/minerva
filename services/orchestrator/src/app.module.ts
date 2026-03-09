import { Module } from '@nestjs/common';
import { OrchestratorConfigModule } from './config/config.module.js';
import { HealthModule } from './health/health.module.js';
import { LoggerModule } from './providers/logger.module.js';

@Module({
  imports: [OrchestratorConfigModule, LoggerModule, HealthModule],
})
export class AppModule {}
