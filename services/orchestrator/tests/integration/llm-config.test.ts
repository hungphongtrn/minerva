import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { afterAll, beforeAll, describe, expect, it, beforeEach, afterEach } from 'vitest';
import { LLM_CONFIG } from '../../dist/config/llm-config.constants.js';
import { LlmConfig } from '../../dist/config/llm.config.js';
import type { Model } from '@mariozechner/pi-ai';

describe('LlmConfig Integration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('startup with valid environment variables', () => {
    let app: INestApplication;

    beforeAll(async () => {
      process.env.LLM_BASE_URL = 'https://api.openai.com/v1';
      process.env.LLM_API_KEY = 'test-api-key';
      process.env.LLM_MODEL = 'gpt-4';

      // Import AppModule dynamically to ensure fresh load with env vars
      const { AppModule } = await import('../../dist/app.module.js');
      
      const moduleRef = await Test.createTestingModule({
        imports: [AppModule],
      }).compile();

      app = moduleRef.createNestApplication();
      await app.init();
    });

    afterAll(async () => {
      if (app) {
        await app.close();
      }
    });

    it('should inject LLM_CONFIG with correct values', () => {
      const llmConfig = app.get(LLM_CONFIG) as LlmConfig;

      expect(llmConfig).toBeInstanceOf(LlmConfig);
      expect(llmConfig.baseUrl).toBe('https://api.openai.com/v1');
      expect(llmConfig.apiKey).toBe('test-api-key');
      expect(llmConfig.model).toBe('gpt-4');
    });

    it('should be able to create a Model object', () => {
      const llmConfig = app.get(LLM_CONFIG) as LlmConfig;
      const model = llmConfig.createModel();

      expect(model).toBeDefined();
      expect(model.id).toBe('gpt-4');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://api.openai.com/v1');
    });
  });

  describe('startup failure with missing environment variables', () => {
    it('should fail to start when LLM_BASE_URL is missing', async () => {
      delete process.env.LLM_BASE_URL;
      process.env.LLM_API_KEY = 'test-api-key';
      process.env.LLM_MODEL = 'gpt-4';

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
    });

    it('should fail to start when LLM_API_KEY is missing', async () => {
      process.env.LLM_BASE_URL = 'https://api.openai.com/v1';
      delete process.env.LLM_API_KEY;
      process.env.LLM_MODEL = 'gpt-4';

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
    });

    it('should fail to start when LLM_MODEL is missing', async () => {
      process.env.LLM_BASE_URL = 'https://api.openai.com/v1';
      process.env.LLM_API_KEY = 'test-api-key';
      delete process.env.LLM_MODEL;

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
    });

    it('should fail to start when all LLM variables are missing', async () => {
      delete process.env.LLM_BASE_URL;
      delete process.env.LLM_API_KEY;
      delete process.env.LLM_MODEL;

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
    });
  });

  describe('startup failure with invalid LLM_BASE_URL', () => {
    it('should fail to start with malformed URL', async () => {
      process.env.LLM_BASE_URL = 'not-a-valid-url';
      process.env.LLM_API_KEY = 'test-api-key';
      process.env.LLM_MODEL = 'gpt-4';

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM_BASE_URL');
    });

    it('should fail to start with empty URL', async () => {
      process.env.LLM_BASE_URL = '';
      process.env.LLM_API_KEY = 'test-api-key';
      process.env.LLM_MODEL = 'gpt-4';

      await expect(LlmConfig.fromEnv()).rejects.toThrow('LLM configuration validation failed');
    });
  });

  describe('using custom model with pi-mono ai package', () => {
    let app: INestApplication;

    beforeAll(async () => {
      process.env.LLM_BASE_URL = 'https://custom.llm.provider.com/api';
      process.env.LLM_API_KEY = 'custom-api-key';
      process.env.LLM_MODEL = 'custom-model-v1';

      const { AppModule } = await import('../../dist/app.module.js');
      
      const moduleRef = await Test.createTestingModule({
        imports: [AppModule],
      }).compile();

      app = moduleRef.createNestApplication();
      await app.init();
    });

    afterAll(async () => {
      if (app) {
        await app.close();
      }
    });

    it('should create Model object compatible with pi-ai package', () => {
      const llmConfig = app.get(LLM_CONFIG) as LlmConfig;
      const model = llmConfig.createModel();

      // Verify model has required fields for pi-ai package
      expect(model.id).toBe('custom-model-v1');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://custom.llm.provider.com/api');
      expect(model.provider).toBe('openai');
      
      // Verify we can get the API key for passing to stream/complete calls
      expect(llmConfig.getApiKey()).toBe('custom-api-key');
    });

    it('should support different model configurations', async () => {
      // Test with OpenAI-style configuration
      process.env.LLM_BASE_URL = 'https://api.openai.com/v1';
      process.env.LLM_API_KEY = 'sk-test123';
      process.env.LLM_MODEL = 'gpt-4-turbo';

      const config = LlmConfig.fromEnv();
      const model = config.createModel();

      expect(model.id).toBe('gpt-4-turbo');
      expect(model.api).toBe('openai-completions');
      expect(config.getApiKey()).toBe('sk-test123');
    });

    it('should support local/self-hosted configurations', async () => {
      // Test with local LLM configuration
      process.env.LLM_BASE_URL = 'http://localhost:8080/v1';
      process.env.LLM_API_KEY = 'local-key';
      process.env.LLM_MODEL = 'llama-2-70b';

      const config = LlmConfig.fromEnv();
      const model = config.createModel();

      expect(model.id).toBe('llama-2-70b');
      expect(model.baseUrl).toBe('http://localhost:8080/v1');
    });
  });
});
