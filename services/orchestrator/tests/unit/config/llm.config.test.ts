import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { LlmConfig, llmEnvSchema } from '../../../src/config/llm.config.js';
import type { Model } from '@mariozechner/pi-ai';

describe('LlmConfig', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('validation', () => {
    it('should validate valid environment variables', () => {
      const env = {
        LLM_BASE_URL: 'https://api.openai.com/v1',
        LLM_API_KEY: 'test-api-key',
        LLM_MODEL: 'gpt-4',
      };

      const result = LlmConfig.validate(env);

      expect(result.LLM_BASE_URL).toBe('https://api.openai.com/v1');
      expect(result.LLM_API_KEY).toBe('test-api-key');
      expect(result.LLM_MODEL).toBe('gpt-4');
    });

    it('should reject missing LLM_BASE_URL', () => {
      const env = {
        LLM_API_KEY: 'test-api-key',
        LLM_MODEL: 'gpt-4',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_BASE_URL');
    });

    it('should reject invalid URL for LLM_BASE_URL', () => {
      const env = {
        LLM_BASE_URL: 'not-a-valid-url',
        LLM_API_KEY: 'test-api-key',
        LLM_MODEL: 'gpt-4',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_BASE_URL');
      expect(() => LlmConfig.validate(env)).toThrow('valid URL');
    });

    it('should reject missing LLM_API_KEY', () => {
      const env = {
        LLM_BASE_URL: 'https://api.openai.com/v1',
        LLM_MODEL: 'gpt-4',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_API_KEY');
    });

    it('should reject empty LLM_API_KEY', () => {
      const env = {
        LLM_BASE_URL: 'https://api.openai.com/v1',
        LLM_API_KEY: '',
        LLM_MODEL: 'gpt-4',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_API_KEY');
    });

    it('should reject missing LLM_MODEL', () => {
      const env = {
        LLM_BASE_URL: 'https://api.openai.com/v1',
        LLM_API_KEY: 'test-api-key',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_MODEL');
    });

    it('should reject empty LLM_MODEL', () => {
      const env = {
        LLM_BASE_URL: 'https://api.openai.com/v1',
        LLM_API_KEY: 'test-api-key',
        LLM_MODEL: '',
      };

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_MODEL');
    });

    it('should reject multiple missing variables with clear error messages', () => {
      const env = {};

      expect(() => LlmConfig.validate(env)).toThrow('LLM configuration validation failed');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_BASE_URL');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_API_KEY');
      expect(() => LlmConfig.validate(env)).toThrow('LLM_MODEL');
    });
  });

  describe('fromEnv', () => {
    it('should create LlmConfig from environment variables', () => {
      process.env.LLM_BASE_URL = 'https://api.openai.com/v1';
      process.env.LLM_API_KEY = 'test-api-key';
      process.env.LLM_MODEL = 'gpt-4';

      const config = LlmConfig.fromEnv();

      expect(config.baseUrl).toBe('https://api.openai.com/v1');
      expect(config.apiKey).toBe('test-api-key');
      expect(config.model).toBe('gpt-4');
    });

    it('should use custom environment object', () => {
      const env = {
        LLM_BASE_URL: 'https://api.custom.com/v1',
        LLM_API_KEY: 'custom-key',
        LLM_MODEL: 'custom-model',
      };

      const config = LlmConfig.fromEnv(env);

      expect(config.baseUrl).toBe('https://api.custom.com/v1');
      expect(config.apiKey).toBe('custom-key');
      expect(config.model).toBe('custom-model');
    });

    it('should throw on invalid environment variables', () => {
      expect(() => LlmConfig.fromEnv({})).toThrow('LLM configuration validation failed');
    });
  });

  describe('createModel', () => {
    it('should create a Model object with correct properties', () => {
      const config = new LlmConfig({
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-api-key',
        model: 'gpt-4',
      });

      const model = config.createModel();

      expect(model.id).toBe('gpt-4');
      expect(model.name).toBe('gpt-4');
      expect(model.api).toBe('openai-completions');
      expect(model.provider).toBe('openai');
      expect(model.baseUrl).toBe('https://api.openai.com/v1');
      expect(model.reasoning).toBe(false);
      expect(model.input).toEqual(['text']);
    });

    it('should create model with custom base URL', () => {
      const config = new LlmConfig({
        baseUrl: 'https://custom.llm.provider.com/api',
        apiKey: 'custom-key',
        model: 'custom-model-v1',
      });

      const model = config.createModel();

      expect(model.baseUrl).toBe('https://custom.llm.provider.com/api');
      expect(model.id).toBe('custom-model-v1');
    });

    it('should create model with minimal required fields for openai-completions API', () => {
      const config = new LlmConfig({
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-api-key',
        model: 'gpt-3.5-turbo',
      });

      const model = config.createModel();

      expect(model.cost).toBeDefined();
      expect(model.contextWindow).toBeGreaterThan(0);
      expect(model.maxTokens).toBeGreaterThan(0);
      expect(model.headers).toBeDefined();
    });
  });

  describe('getApiKey', () => {
    it('should return the API key', () => {
      const config = new LlmConfig({
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'my-secret-api-key',
        model: 'gpt-4',
      });

      expect(config.getApiKey()).toBe('my-secret-api-key');
    });
  });

  describe('schema validation', () => {
    it('should accept valid URLs', () => {
      const validUrls = [
        'https://api.openai.com/v1',
        'http://localhost:8080',
        'https://custom.provider.com/api/v2',
      ];

      for (const url of validUrls) {
        const result = llmEnvSchema.safeParse({
          LLM_BASE_URL: url,
          LLM_API_KEY: 'key',
          LLM_MODEL: 'model',
        });

        expect(result.success).toBe(true);
      }
    });

    it('should reject invalid URLs', () => {
      const invalidUrls = [
        'not-a-url',
        'just-text',
      ];

      for (const url of invalidUrls) {
        const result = llmEnvSchema.safeParse({
          LLM_BASE_URL: url,
          LLM_API_KEY: 'key',
          LLM_MODEL: 'model',
        });

        expect(result.success).toBe(false);
      }
    });

    it('should reject empty URL', () => {
      const result = llmEnvSchema.safeParse({
        LLM_BASE_URL: '',
        LLM_API_KEY: 'key',
        LLM_MODEL: 'model',
      });

      // Empty string fails the URL validation in zod
      expect(result.success).toBe(false);
    });
  });
});
