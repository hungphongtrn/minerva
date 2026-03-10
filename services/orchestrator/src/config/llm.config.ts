import { Injectable } from '@nestjs/common';
import { z } from 'zod';
import type { Model } from '@mariozechner/pi-ai';

export const llmEnvSchema = z.object({
  LLM_BASE_URL: z.string().url('LLM_BASE_URL must be a valid URL'),
  LLM_API_KEY: z.string().min(1, 'LLM_API_KEY is required'),
  LLM_MODEL: z.string().min(1, 'LLM_MODEL is required'),
});

export type LlmEnvConfig = z.infer<typeof llmEnvSchema>;

export interface LlmConfigOptions {
  baseUrl: string;
  apiKey: string;
  model: string;
}

@Injectable()
export class LlmConfig {
  readonly baseUrl: string;
  readonly apiKey: string;
  readonly model: string;

  constructor(options: LlmConfigOptions) {
    this.baseUrl = options.baseUrl;
    this.apiKey = options.apiKey;
    this.model = options.model;
  }

  /**
   * Creates a custom Model object compatible with @mariozechner/pi-ai package.
   * Uses the generic LLM_* environment variables instead of provider-specific ones.
   * 
   * Note: This creates a minimal Model with sensible defaults for fields that aren't
   * critical for the openai-completions API (cost, contextWindow, maxTokens, etc.).
   */
  createModel(): Model<'openai-completions'> {
    const model: Model<'openai-completions'> = {
      id: this.model,
      name: this.model,
      api: 'openai-completions',
      provider: 'openai',
      baseUrl: this.baseUrl,
      reasoning: false,
      input: ['text'],
      cost: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
      },
      contextWindow: 128000,
      maxTokens: 4096,
      headers: {},
      compat: undefined,
    };
    return model;
  }

  /**
   * Returns the API key for use with pi-mono ai package.
   * This should be passed explicitly to stream() or complete() calls via options.apiKey.
   */
  getApiKey(): string {
    return this.apiKey;
  }

  /**
   * Validates environment variables and returns parsed config.
   * Throws an error if validation fails (fail-fast).
   */
  static validate(env: Record<string, unknown>): LlmEnvConfig {
    const result = llmEnvSchema.safeParse(env);

    if (!result.success) {
      const errors = result.error.issues
        .map((issue: z.ZodIssue) => `${issue.path.join('.')}: ${issue.message}`)
        .join('\n');
      throw new Error(`LLM configuration validation failed:\n${errors}`);
    }

    return result.data;
  }

  /**
   * Creates LlmConfig from environment variables.
   * Validates and throws if configuration is invalid.
   */
  static fromEnv(env: Record<string, unknown> = process.env): LlmConfig {
    const config = LlmConfig.validate(env);
    return new LlmConfig({
      baseUrl: config.LLM_BASE_URL,
      apiKey: config.LLM_API_KEY,
      model: config.LLM_MODEL,
    });
  }
}
