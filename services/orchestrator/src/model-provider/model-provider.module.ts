import { Global, Module } from '@nestjs/common';
import { ModelProviderConfig } from './model-provider.config.js';
import { MODEL_PROVIDER_CONFIG } from './model-provider.constants.js';
import { ModelProviderService } from './model-provider.service.js';

@Global()
@Module({
  providers: [
    {
      provide: MODEL_PROVIDER_CONFIG,
      useFactory: (): ModelProviderConfig => {
        try {
          return ModelProviderConfig.fromEnv();
        } catch (error) {
          // Log the error and re-throw to fail fast
          console.error('Failed to initialize model provider configuration:', error);
          throw error;
        }
      },
    },
    ModelProviderService,
  ],
  exports: [MODEL_PROVIDER_CONFIG, ModelProviderService],
})
export class ModelProviderModule {}
