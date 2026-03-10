import { Injectable, Inject } from '@nestjs/common';
import type { StreamFn } from '@mariozechner/pi-agent-core';
import type { Model, Context, AssistantMessageEventStream } from '@mariozechner/pi-ai';
import { streamSimple } from '@mariozechner/pi-ai';
import { ModelProviderConfig } from './model-provider.config.js';
import { MODEL_PROVIDER_CONFIG } from './model-provider.constants.js';
import { LOGGER } from '../providers/provider-tokens.js';
import type { ILogger } from '../providers/types.js';

export interface ProviderHealthStatus {
  healthy: boolean;
  provider: string;
  message: string;
  error?: string;
}

@Injectable()
export class ModelProviderService {
  constructor(
    @Inject(MODEL_PROVIDER_CONFIG) private readonly config: ModelProviderConfig,
    @Inject(LOGGER) private readonly logger: ILogger
  ) {}

  /**
   * Returns the configured provider type.
   */
  getProviderType(): string {
    return this.config.provider;
  }

  /**
   * Creates the stream function for the configured provider.
   * This is the main factory method that returns a StreamFn compatible with pi-agent-core.
   */
  createStreamFn(): StreamFn {
    return async (
      model: Model<any>,
      context: Context
    ): Promise<AssistantMessageEventStream> => {
      const apiKey = this.config.getApiKey();
      const temperature = this.config.temperature;
      const maxTokens = this.config.maxTokens;

      this.logger.debug('Creating stream for provider', {
        provider: this.config.provider,
        model: model.id,
      });

      try {
        const result = await streamSimple(model, context, {
          apiKey,
          temperature,
          maxTokens,
        });

        return result;
      } catch (error) {
        this.logger.error('Stream creation failed', error instanceof Error ? error : undefined, {
          provider: this.config.provider,
          model: model.id,
        });
        throw error;
      }
    };
  }

  /**
   * Gets the Model configuration for the configured provider.
   */
  getModel(): Model<any> {
    return this.config.createModel();
  }

  /**
   * Performs a health check on the configured provider.
   * Returns status information about provider connectivity.
   */
  async checkHealth(): Promise<ProviderHealthStatus> {
    try {
      // Validate that we have the required configuration
      const apiKey = this.config.getApiKey();

      if (!apiKey || apiKey.length === 0) {
        return {
          healthy: false,
          provider: this.config.provider,
          message: `API key not configured for ${this.config.provider}`,
          error: 'Missing API key',
        };
      }

      // Basic validation of API key format
      if (!this.isValidApiKeyFormat(apiKey)) {
        return {
          healthy: false,
          provider: this.config.provider,
          message: `Invalid API key format for ${this.config.provider}`,
          error: 'API key format validation failed',
        };
      }

      // For now, we do basic validation only
      // In production, you might want to make a lightweight API call to verify connectivity
      return {
        healthy: true,
        provider: this.config.provider,
        message: `${this.config.provider} provider configured successfully`,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('Health check failed', error instanceof Error ? error : undefined, {
        provider: this.config.provider,
      });

      return {
        healthy: false,
        provider: this.config.provider,
        message: `Health check failed for ${this.config.provider}`,
        error: errorMessage,
      };
    }
  }

  /**
   * Validates the API key format for the configured provider.
   */
  private isValidApiKeyFormat(apiKey: string): boolean {
    if (this.config.provider === 'openai') {
      // OpenAI keys typically start with 'sk-'
      return apiKey.startsWith('sk-');
    }

    if (this.config.provider === 'anthropic') {
      // Anthropic keys typically start with 'sk-ant-'
      return apiKey.startsWith('sk-ant-');
    }

    return false;
  }

  /**
   * Returns configuration information for the provider.
   * Useful for debugging and logging.
   */
  getProviderInfo(): {
    provider: string;
    model: string;
    temperature?: number;
    maxTokens?: number;
  } {
    return {
      provider: this.config.provider,
      model: this.config.getModelName(),
      temperature: this.config.temperature,
      maxTokens: this.config.maxTokens,
    };
  }
}
