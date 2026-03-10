import { describe, it, expect, beforeEach } from 'vitest';
import {
  ModelProviderConfig,
  modelProviderConfigSchema,
  modelProviderTypeSchema,
} from '../../src/model-provider/model-provider.config.js';

describe('ModelProviderConfig', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Reset environment before each test
    process.env = { ...originalEnv };
    delete process.env.MODEL_PROVIDER;
    delete process.env.OPENAI_API_KEY;
    delete process.env.ANTHROPIC_API_KEY;
    delete process.env.MODEL_NAME;
    delete process.env.MODEL_TEMPERATURE;
    delete process.env.MODEL_MAX_TOKENS;
  });

  describe('schema validation', () => {
    it('should validate valid openai configuration', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: 'sk-test123',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.MODEL_PROVIDER).toBe('openai');
        expect(result.data.OPENAI_API_KEY).toBe('sk-test123');
      }
    });

    it('should validate valid anthropic configuration', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: 'sk-ant-test123',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.MODEL_PROVIDER).toBe('anthropic');
        expect(result.data.ANTHROPIC_API_KEY).toBe('sk-ant-test123');
      }
    });

    it('should reject invalid provider type', () => {
      const env = {
        MODEL_PROVIDER: 'invalid-provider',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(false);
    });

    it('should reject temperature outside valid range', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        MODEL_TEMPERATURE: '3.0', // Too high
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(false);
    });

    it('should reject negative temperature', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        MODEL_TEMPERATURE: '-0.5',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(false);
    });

    it('should reject non-positive max tokens', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        MODEL_MAX_TOKENS: '0',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(false);
    });

    it('should accept valid optional parameters', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: 'sk-test123',
        MODEL_NAME: 'gpt-4-turbo',
        MODEL_TEMPERATURE: '0.7',
        MODEL_MAX_TOKENS: '4096',
      };

      const result = modelProviderConfigSchema.safeParse(env);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.MODEL_NAME).toBe('gpt-4-turbo');
        expect(result.data.MODEL_TEMPERATURE).toBe(0.7);
        expect(result.data.MODEL_MAX_TOKENS).toBe(4096);
      }
    });
  });

  describe('fromEnv', () => {
    it('should create config from environment with openai provider', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
        OPENAI_API_KEY: 'sk-test123',
        MODEL_NAME: 'gpt-4-turbo',
        MODEL_TEMPERATURE: '0.5',
        MODEL_MAX_TOKENS: '2048',
      };

      const config = ModelProviderConfig.fromEnv(env);

      expect(config.provider).toBe('openai');
      expect(config.openaiApiKey).toBe('sk-test123');
      expect(config.modelName).toBe('gpt-4-turbo');
      expect(config.temperature).toBe(0.5);
      expect(config.maxTokens).toBe(2048);
    });

    it('should create config from environment with anthropic provider', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
        ANTHROPIC_API_KEY: 'sk-ant-test123',
        MODEL_NAME: 'claude-3-opus-20240229',
        MODEL_TEMPERATURE: '0.8',
        MODEL_MAX_TOKENS: '8192',
      };

      const config = ModelProviderConfig.fromEnv(env);

      expect(config.provider).toBe('anthropic');
      expect(config.anthropicApiKey).toBe('sk-ant-test123');
      expect(config.modelName).toBe('claude-3-opus-20240229');
      expect(config.temperature).toBe(0.8);
      expect(config.maxTokens).toBe(8192);
    });

    it('should throw error for missing MODEL_PROVIDER', () => {
      const env = {};

      expect(() => ModelProviderConfig.fromEnv(env)).toThrow(
        'MODEL_PROVIDER must be "openai" or "anthropic"'
      );
    });

    it('should throw error when openai provider is selected but no OPENAI_API_KEY', () => {
      const env = {
        MODEL_PROVIDER: 'openai',
      };

      expect(() => ModelProviderConfig.fromEnv(env)).toThrow(
        'OPENAI_API_KEY is required when MODEL_PROVIDER=openai'
      );
    });

    it('should throw error when anthropic provider is selected but no ANTHROPIC_API_KEY', () => {
      const env = {
        MODEL_PROVIDER: 'anthropic',
      };

      expect(() => ModelProviderConfig.fromEnv(env)).toThrow(
        'ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic'
      );
    });
  });

  describe('getApiKey', () => {
    it('should return openai api key for openai provider', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });

      expect(config.getApiKey()).toBe('sk-test123');
    });

    it('should return anthropic api key for anthropic provider', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
      });

      expect(config.getApiKey()).toBe('sk-ant-test123');
    });

    it('should throw error when openai api key is missing', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
      });

      expect(() => config.getApiKey()).toThrow(
        'OPENAI_API_KEY is required when MODEL_PROVIDER=openai'
      );
    });

    it('should throw error when anthropic api key is missing', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
      });

      expect(() => config.getApiKey()).toThrow(
        'ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic'
      );
    });
  });

  describe('getModelName', () => {
    it('should return configured model name when provided', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        modelName: 'gpt-4-turbo',
      });

      expect(config.getModelName()).toBe('gpt-4-turbo');
    });

    it('should return default openai model when not configured', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
      });

      expect(config.getModelName()).toBe('gpt-4-turbo-preview');
    });

    it('should return default anthropic model when not configured', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
      });

      expect(config.getModelName()).toBe('claude-3-opus-20240229');
    });
  });

  describe('createModel', () => {
    it('should create model object for openai provider', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
        modelName: 'gpt-4-turbo',
        maxTokens: 8192,
      });

      const model = config.createModel();

      expect(model.id).toBe('gpt-4-turbo');
      expect(model.name).toBe('gpt-4-turbo');
      expect(model.provider).toBe('openai');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://api.openai.com/v1');
      expect(model.maxTokens).toBe(8192);
    });

    it('should create model object for anthropic provider', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
        modelName: 'claude-3-opus-20240229',
        maxTokens: 4096,
      });

      const model = config.createModel();

      expect(model.id).toBe('claude-3-opus-20240229');
      expect(model.name).toBe('claude-3-opus-20240229');
      expect(model.provider).toBe('anthropic');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://api.anthropic.com/v1');
      expect(model.maxTokens).toBe(4096);
    });

    it('should use default max tokens when not specified', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });

      const model = config.createModel();

      expect(model.maxTokens).toBe(4096);
    });
  });
});

describe('modelProviderTypeSchema', () => {
  it('should accept "openai" as valid provider', () => {
    const result = modelProviderTypeSchema.safeParse('openai');
    expect(result.success).toBe(true);
  });

  it('should accept "anthropic" as valid provider', () => {
    const result = modelProviderTypeSchema.safeParse('anthropic');
    expect(result.success).toBe(true);
  });

  it('should reject other provider types', () => {
    const result = modelProviderTypeSchema.safeParse('google');
    expect(result.success).toBe(false);
  });
});
