## Why

The orchestrator currently uses a scripted runtime that generates fake events for demonstration purposes. To execute actual agent runs, we need to integrate with a real LLM provider. This change replaces the scripted runtime with a configurable real model provider integration using pi-agent-core, enabling the system to perform actual AI-driven agent loops with real tool execution and streaming responses.

## What Changes

- **Add provider abstraction layer** for configurable LLM backends (OpenAI, Anthropic, etc.) with pluggable provider interface
- **Replace scripted model wiring** in the runtime path with real model provider integration using pi-agent-core
- **Add configuration and secrets management** for model provider credentials (API keys, endpoints) with validation at startup
- **Update run orchestration** to instantiate and use real model clients instead of scripted event generators
- **Add integration test coverage** for real model execution behavior including streaming, tool usage, and cancellation
- **Update documentation** with setup instructions and sample environment configuration

**Non-goals (deferred):**
- Multi-model routing or provider fallback (v1)
- Provider-agnostic tool schemas beyond pi-agent-core's capabilities
- Fine-grained model parameter tuning beyond basic configuration

## Capabilities

### New Capabilities
- `model-provider`: Abstraction layer for LLM provider integration, configuration, and credential management. Enables pluggable backend support with validation and health checks.

### Modified Capabilities
- `run-orchestration`: Update requirements to use real model provider instead of scripted runtime. The agent loop will now make actual LLM calls and process real responses instead of generating synthetic events.

## Impact

- **Runtime**: Complete replacement of scripted event generator with pi-agent-core integration
- **Configuration**: New environment variables for model provider settings (API keys, model names, endpoints)
- **API**: No breaking API changes - existing SSE endpoints and run lifecycle remain compatible
- **Dependencies**: Requires pi-agent-core package and provider-specific SDKs (e.g., openai)
- **Testing**: New integration tests requiring real API keys (marked accordingly)
- **Documentation**: Setup guide updates for provider configuration
