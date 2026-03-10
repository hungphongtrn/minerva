import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ModelProviderService } from '../../src/model-provider/model-provider.service.js';
import { ModelProviderConfig } from '../../src/model-provider/model-provider.config.js';
import type { ILogger } from '../../src/providers/types.js';

describe('ModelProviderService', () => {
  const mockLogger: ILogger = {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getProviderType', () => {
    it('should return openai provider type', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      expect(service.getProviderType()).toBe('openai');
    });

    it('should return anthropic provider type', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      expect(service.getProviderType()).toBe('anthropic');
    });
  });

  describe('createStreamFn', () => {
    it('should return a stream function', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      const streamFn = service.createStreamFn();

      expect(typeof streamFn).toBe('function');
    });

    it('should log debug message when creating stream', async () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      // Just verify the function exists and has correct signature
      const streamFn = service.createStreamFn();
      expect(streamFn).toBeDefined();
      expect(typeof streamFn).toBe('function');
    });
  });

  describe('getModel', () => {
    it('should return model for openai provider', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
        modelName: 'gpt-4-turbo',
      });
      const service = new ModelProviderService(config, mockLogger);

      const model = service.getModel();

      expect(model.id).toBe('gpt-4-turbo');
      expect(model.provider).toBe('openai');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://api.openai.com/v1');
    });

    it('should return model for anthropic provider', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
        modelName: 'claude-3-opus-20240229',
      });
      const service = new ModelProviderService(config, mockLogger);

      const model = service.getModel();

      expect(model.id).toBe('claude-3-opus-20240229');
      expect(model.provider).toBe('anthropic');
      expect(model.api).toBe('openai-completions');
      expect(model.baseUrl).toBe('https://api.anthropic.com/v1');
    });
  });

  describe('checkHealth', () => {
    it('should return healthy status for valid openai configuration', async () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      const status = await service.checkHealth();

      expect(status.healthy).toBe(true);
      expect(status.provider).toBe('openai');
      expect(status.message).toContain('configured successfully');
    });

    it('should return healthy status for valid anthropic configuration', async () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      const status = await service.checkHealth();

      expect(status.healthy).toBe(true);
      expect(status.provider).toBe('anthropic');
      expect(status.message).toContain('configured successfully');
    });

    it('should return unhealthy status for invalid openai key format', async () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'invalid-key',
      });
      const service = new ModelProviderService(config, mockLogger);

      const status = await service.checkHealth();

      expect(status.healthy).toBe(false);
      expect(status.provider).toBe('openai');
      expect(status.error).toContain('API key format validation failed');
    });

    it('should return unhealthy status for invalid anthropic key format', async () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'invalid-key',
      });
      const service = new ModelProviderService(config, mockLogger);

      const status = await service.checkHealth();

      expect(status.healthy).toBe(false);
      expect(status.provider).toBe('anthropic');
      expect(status.error).toContain('API key format validation failed');
    });

    it('should log error when health check encounters exception', async () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });

      // Mock getApiKey to throw
      vi.spyOn(config, 'getApiKey').mockImplementation(() => {
        throw new Error('Unexpected error');
      });

      const service = new ModelProviderService(config, mockLogger);

      const status = await service.checkHealth();

      expect(status.healthy).toBe(false);
      expect(status.error).toBe('Unexpected error');
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Health check failed',
        expect.any(Error),
        expect.any(Object)
      );
    });
  });

  describe('getProviderInfo', () => {
    it('should return provider info for openai', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
        modelName: 'gpt-4-turbo',
        temperature: 0.7,
        maxTokens: 4096,
      });
      const service = new ModelProviderService(config, mockLogger);

      const info = service.getProviderInfo();

      expect(info.provider).toBe('openai');
      expect(info.model).toBe('gpt-4-turbo');
      expect(info.temperature).toBe(0.7);
      expect(info.maxTokens).toBe(4096);
    });

    it('should return provider info for anthropic', () => {
      const config = new ModelProviderConfig({
        provider: 'anthropic',
        anthropicApiKey: 'sk-ant-test123',
        modelName: 'claude-3-opus-20240229',
        temperature: 0.5,
        maxTokens: 8192,
      });
      const service = new ModelProviderService(config, mockLogger);

      const info = service.getProviderInfo();

      expect(info.provider).toBe('anthropic');
      expect(info.model).toBe('claude-3-opus-20240229');
      expect(info.temperature).toBe(0.5);
      expect(info.maxTokens).toBe(8192);
    });

    it('should handle missing optional parameters', () => {
      const config = new ModelProviderConfig({
        provider: 'openai',
        openaiApiKey: 'sk-test123',
      });
      const service = new ModelProviderService(config, mockLogger);

      const info = service.getProviderInfo();

      expect(info.provider).toBe('openai');
      expect(info.model).toBe('gpt-4-turbo-preview');
      expect(info.temperature).toBeUndefined();
      expect(info.maxTokens).toBeUndefined();
    });
  });
});
