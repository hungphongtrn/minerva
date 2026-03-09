import { Global, Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { loadConfig } from './index.js';
import { ORCHESTRATOR_CONFIG } from './config.constants.js';
import type { OrchestratorConfig } from './types.js';

@Global()
@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      cache: true,
    }),
  ],
  providers: [
    {
      provide: ORCHESTRATOR_CONFIG,
      useFactory: (): OrchestratorConfig => loadConfig(),
    },
  ],
  exports: [ORCHESTRATOR_CONFIG],
})
export class OrchestratorConfigModule {}
