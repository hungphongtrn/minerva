import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { ModelProviderConfig } from '../../src/model-provider/model-provider.config.js';
import { ModelProviderService } from '../../src/model-provider/model-provider.service.js';
import type { ILogger } from '../../src/providers/types.js';

/**
 * Integration tests for Model Provider
 * 
 * These tests require real API keys and will be skipped if not available.
 * Run these tests with valid API keys to verify real provider connectivity.
 */

const mockLogger: ILogger = {
  debug: console.log,
  info: console.log,
  warn: console.warn,
  error: console.error,
};

describe('Model Provider Integration', () => {
  describe('OpenAI Provider', () => {
    const openaiKey = process.env.OPENAI_API_KEY;
    const hasOpenAIKey = openaiKey && openaiKey.startsWith('sk-');

    beforeAll(() => {
      if (!hasOpenAIKey) {
        console.log('Skipping OpenAI integration tests - no valid API key');
      }
    });

    beforeEach(() => {
      if (hasOpenAIKey) {
        // Small delay to avoid rate limits
        return new Promise(resolve => setTimeout(resolve, 1000));
      }
    });

    it.skipIf(!hasOpenAIKey)('should validate configuration', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: openaiKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      
      expect(config.provider).toBe('openai');
      expect(config.getApiKey()).toBe(openaiKey);
      expect(config.getModelName()).toBe('gpt-4-turbo-preview');
    });

    it.skipIf(!hasOpenAIKey)('should pass health check', async () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: openaiKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const health = await service.checkHealth();
      
      expect(health.healthy).toBe(true);
      expect(health.provider).toBe('openai');
    });

    it.skipIf(!hasOpenAIKey)('should create model configuration', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: openaiKey,
        MODEL_NAME: 'gpt-4',
        MODEL_TEMPERATURE: '0.5',
        MODEL_MAX_TOKENS: '2048',
      };

      const config = ModelProviderConfig.fromEnv(env);
      const model = config.createModel();
      
      expect(model.id).toBe('gpt-4');
      expect(model.provider).toBe('openai');
      expect(model.baseUrl).toBe('https://api.openai.com/v1');
      expect(model.maxTokens).toBe(2048);
    });

    it.skipIf(!hasOpenAIKey)('should create stream function', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: openaiKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const streamFn = service.createStreamFn();
      
      expect(typeof streamFn).toBe('function');
    });
  });

  describe('Anthropic Provider', () => {
    const anthropicKey = process.env.ANTHROPIC_API_KEY;
    const hasAnthropicKey = anthropicKey && anthropicKey.startsWith('sk-ant-');

    beforeAll(() => {
      if (!hasAnthropicKey) {
        console.log('Skipping Anthropic integration tests - no valid API key');
      }
    });

    beforeEach(() => {
      if (hasAnthropicKey) {
        // Small delay to avoid rate limits
        return new Promise(resolve => setTimeout(resolve, 1000));
      }
    });

    it.skipIf(!hasAnthropicKey)('should validate configuration', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: anthropicKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      
      expect(config.provider).toBe('anthropic');
      expect(config.getApiKey()).toBe(anthropicKey);
      expect(config.getModelName()).toBe('claude-3-opus-20240229');
    });

    it.skipIf(!hasAnthropicKey)('should pass health check', async () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: anthropicKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const health = await service.checkHealth();
      
      expect(health.healthy).toBe(true);
      expect(health.provider).toBe('anthropic');
    });

    it.skipIf(!hasAnthropicKey)('should create model configuration', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: anthropicKey,
        MODEL_NAME: 'claude-3-sonnet-20240229',
        MODEL_TEMPERATURE: '0.8',
        MODEL_MAX_TOKENS: '4096',
      };

      const config = ModelProviderConfig.fromEnv(env);
      const model = config.createModel();
      
      expect(model.id).toBe('claude-3-sonnet-20240229');
      expect(model.provider).toBe('anthropic');
      expect(model.baseUrl).toBe('https://api.anthropic.com/v1');
      expect(model.maxTokens).toBe(4096);
    });

    it.skipIf(!hasAnthropicKey)('should create stream function', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: anthropicKey,
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const streamFn = service.createStreamFn();
      
      expect(typeof streamFn).toBe('function');
    });
  });

  describe('Health Check Validation', () => {
    it('should detect invalid OpenAI key format', async () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: 'invalid-key',
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const health = await service.checkHealth();
      
      expect(health.healthy).toBe(false);
      expect(health.error).toContain('API key format validation failed');
    });

    it('should detect invalid Anthropic key format', async () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: 'invalid-key',
      };

      const config = ModelProviderConfig.fromEnv(env);
      const service = new ModelProviderService(config, mockLogger);
      
      const health = await service.checkHealth();
      
      expect(health.healthy).toBe(false);
      expect(health.error).toContain('API key format validation failed');
    });
  });
});
