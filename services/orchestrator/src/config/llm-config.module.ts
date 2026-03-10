import { Global, Module } from '@nestjs/common';
import { LlmConfig } from './llm.config.js';
import { LLM_CONFIG } from './llm-config.constants.js';

@Global()
@Module({
  providers: [
    {
      provide: LLM_CONFIG,
      useFactory: (): LlmConfig => LlmConfig.fromEnv(),
    },
  ],
  exports: [LLM_CONFIG],
})
export class LlmConfigModule {}
