import { Module } from '@nestjs/common';
import { OrchestratorConfigModule } from './config/config.module.js';
import { LlmConfigModule } from './config/llm-config.module.js';
import { HealthModule } from './health/health.module.js';
import { LoggerModule } from './providers/logger.module.js';
import { RunsModule } from './runs/runs.module.js';
import { RuntimeModule } from './runtime/runtime.module.js';
import { SSEModule } from './sse/sse.module.js';

@Module({
  imports: [
    OrchestratorConfigModule,
    LlmConfigModule,
    LoggerModule,
    HealthModule,
    RuntimeModule,
    RunsModule,
    SSEModule,
  ],
})
export class AppModule {}
