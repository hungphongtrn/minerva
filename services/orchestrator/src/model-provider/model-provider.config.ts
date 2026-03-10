import { Injectable } from '@nestjs/common';
import { z } from 'zod';
import type { Model } from '@mariozechner/pi-ai';

export const modelProviderTypeSchema = z.enum(['openai', 'anthropic'], {
  errorMap: () => ({ message: 'MODEL_PROVIDER must be "openai" or "anthropic"' }),
});

export type ModelProviderType = z.infer<typeof modelProviderTypeSchema>;

export const modelProviderConfigSchema = z.object({
  MODEL_PROVIDER: modelProviderTypeSchema,
  OPENAI_API_KEY: z.string().optional(),
  ANTHROPIC_API_KEY: z.string().optional(),
  MODEL_NAME: z.string().min(1, 'MODEL_NAME cannot be empty').optional(),
  MODEL_TEMPERATURE: z.coerce.number().min(0).max(2).optional(),
  MODEL_MAX_TOKENS: z.coerce.number().int().positive().optional(),
});

export type ModelProviderEnvConfig = z.infer<typeof modelProviderConfigSchema>;

export interface ModelProviderConfigOptions {
  provider: ModelProviderType;
  openaiApiKey?: string;
  anthropicApiKey?: string;
  modelName?: string;
  temperature?: number;
  maxTokens?: number;
}

@Injectable()
export class ModelProviderConfig {
  readonly provider: ModelProviderType;
  readonly openaiApiKey?: string;
  readonly anthropicApiKey?: string;
  readonly modelName?: string;
  readonly temperature?: number;
  readonly maxTokens?: number;

  constructor(options: ModelProviderConfigOptions) {
    this.provider = options.provider;
    this.openaiApiKey = options.openaiApiKey;
    this.anthropicApiKey = options.anthropicApiKey;
    this.modelName = options.modelName;
    this.temperature = options.temperature;
    this.maxTokens = options.maxTokens;
  }

  /**
   * Returns the API key for the configured provider.
   * Throws if the required key is not available.
   */
  getApiKey(): string {
    if (this.provider === 'openai') {
      if (!this.openaiApiKey) {
        throw new Error('OPENAI_API_KEY is required when MODEL_PROVIDER=openai');
      }
      return this.openaiApiKey;
    }

    if (this.provider === 'anthropic') {
      if (!this.anthropicApiKey) {
        throw new Error('ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic');
      }
      return this.anthropicApiKey;
    }

    throw new Error(`Unknown provider: ${this.provider}`);
  }

  /**
   * Returns the model name with fallback to provider defaults.
   */
  getModelName(): string {
    if (this.modelName) {
      return this.modelName;
    }

    // Default models per provider
    if (this.provider === 'openai') {
      return 'gpt-4-turbo-preview';
    }

    if (this.provider === 'anthropic') {
      return 'claude-3-opus-20240229';
    }

    throw new Error(`Unknown provider: ${this.provider}`);
  }

  /**
   * Creates a Model object compatible with @mariozechner/pi-ai package.
   */
  createModel(): Model<'openai-completions'> {
    const modelName = this.getModelName();

    const model: Model<'openai-completions'> = {
      id: modelName,
      name: modelName,
      api: 'openai-completions',
      provider: this.provider,
      baseUrl: this.getProviderBaseUrl(),
      reasoning: false,
      input: ['text'],
      cost: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
      },
      contextWindow: 128000,
      maxTokens: this.maxTokens ?? 4096,
      headers: {},
    };

    return model;
  }

  /**
   * Returns the base URL for the configured provider.
   */
  private getProviderBaseUrl(): string {
    if (this.provider === 'openai') {
      return 'https://api.openai.com/v1';
    }

    if (this.provider === 'anthropic') {
      return 'https://api.anthropic.com/v1';
    }

    throw new Error(`Unknown provider: ${this.provider}`);
  }

  /**
   * Validates environment variables and returns parsed config.
   * Throws an error with descriptive message if validation fails (fail-fast).
   */
  static validate(env: Record<string, unknown>): ModelProviderEnvConfig {
    const result = modelProviderConfigSchema.safeParse(env);

    if (!result.success) {
      const errors = result.error.issues
        .map((issue: z.ZodIssue) => `${issue.path.join('.')}: ${issue.message}`)
        .join('\n');
      throw new Error(`Model provider configuration validation failed:\n${errors}`);
    }

    const config = result.data;

    // Validate provider-specific API keys
    if (config.MODEL_PROVIDER === 'openai' && !config.OPENAI_API_KEY) {
      throw new Error(
        'Model provider configuration validation failed:\nOPENAI_API_KEY is required when MODEL_PROVIDER=openai'
      );
    }

    if (config.MODEL_PROVIDER === 'anthropic' && !config.ANTHROPIC_API_KEY) {
      throw new Error(
        'Model provider configuration validation failed:\nANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic'
      );
    }

    return config;
  }

  /**
   * Creates ModelProviderConfig from environment variables.
   * Validates and throws if configuration is invalid.
   */
  static fromEnv(env: Record<string, unknown> = process.env): ModelProviderConfig {
    const config = ModelProviderConfig.validate(env);

    return new ModelProviderConfig({
      provider: config.MODEL_PROVIDER,
      openaiApiKey: config.OPENAI_API_KEY,
      anthropicApiKey: config.ANTHROPIC_API_KEY,
      modelName: config.MODEL_NAME,
      temperature: config.MODEL_TEMPERATURE,
      maxTokens: config.MODEL_MAX_TOKENS,
    });
  }
}
