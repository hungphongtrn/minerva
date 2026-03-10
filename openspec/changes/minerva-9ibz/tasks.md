## 1. Provider Configuration Module

- [x] 1.1 Create `ModelProviderConfig` class with Zod schema for environment validation
- [x] 1.2 Add environment variable definitions (MODEL_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY, MODEL_NAME, MODEL_TEMPERATURE, MODEL_MAX_TOKENS)
- [x] 1.3 Implement configuration validation at module initialization with descriptive error messages
- [x] 1.4 Add NestJS ConfigModule registration for provider settings
- [x] 1.5 Create unit tests for configuration validation (valid/invalid cases)

## 2. Model Provider Service

- [x] 2.1 Create `ModelProviderService` with provider factory method
- [x] 2.2 Implement OpenAI provider adapter using pi-agent-core
- [x] 2.3 Implement Anthropic provider adapter using pi-agent-core
- [x] 2.4 Add health check method to verify provider connectivity
- [x] 2.5 Register service in NestJS dependency injection container
- [x] 2.6 Create unit tests for provider service with mocked SDKs

## 3. Health Check Integration

- [x] 3.1 Add provider health check to existing health endpoint
- [x] 3.2 Implement connectivity test for configured provider
- [x] 3.3 Return appropriate status codes (200 healthy, 503 unhealthy)
- [x] 3.4 Add unit tests for health check behavior

## 4. Run Orchestration Updates

- [x] 4.1 Modify `RunService` to inject `ModelProviderService`
- [x] 4.2 Replace scripted event generator with pi-agent-core initialization
- [x] 4.3 Implement event translation layer (pi-agent-core events → SSE format)
- [x] 4.4 Add provider availability check before run start
- [x] 4.5 Implement provider error handling (rate limits, auth failures, timeouts)
- [x] 4.6 Update run initialization to use configured model parameters
- [x] 4.7 Ensure tool execution integration with sandbox works with real LLM calls
- [x] 4.8 Add unit tests for run service with mocked provider

## 5. Integration and End-to-End Testing

- [x] 5.1 Create integration test for OpenAI provider (requires API key)
- [x] 5.2 Create integration test for Anthropic provider (requires API key)
- [x] 5.3 Add end-to-end test for complete run flow with real provider
- [x] 5.4 Test streaming events are emitted correctly
- [x] 5.5 Test cancellation and timeout handling with real provider
- [x] 5.6 Test tool execution (read/write/bash) in sandbox with real LLM
- [x] 5.7 Mark integration tests to skip when API keys not available

## 6. Documentation and Configuration

- [x] 6.1 Update `.env.example` with all new provider configuration variables
- [x] 6.2 Create `docs/model-provider-setup.md` with setup instructions
- [x] 6.3 Document provider-specific requirements (API key permissions, model availability)
- [x] 6.4 Add troubleshooting guide for common configuration errors
- [x] 6.5 Update architecture docs to reflect real provider integration

## 7. Cleanup and Migration

- [x] 7.1 Remove scripted runtime code (or mark as deprecated if keeping for testing)
- [x] 7.2 Update any demo/test code that relied on scripted behavior
- [x] 7.3 Verify no references to scripted generator in production code paths
- [x] 7.4 Run full test suite to ensure no regressions
- [x] 7.5 Verify health endpoint reports provider status correctly in deployed environment
