## Context

The orchestrator currently uses a scripted runtime that generates synthetic events to simulate agent behavior. This was useful for early development and testing the SSE streaming infrastructure, but the system needs to execute real agent runs using actual LLM providers.

The project uses pi-agent-core as the agent runtime library, which provides a framework for building agent loops with streaming responses, tool execution, and cancellation support. However, the current orchestrator implementation bypasses pi-agent-core's model provider integration and uses a hardcoded scripted generator instead.

This design document outlines how to integrate real LLM providers into the orchestrator while maintaining compatibility with existing APIs and preserving the event streaming behavior that clients already depend on.

## Goals / Non-Goals

**Goals:**
- Replace scripted runtime with real model provider integration using pi-agent-core
- Support configurable LLM providers (OpenAI, Anthropic) via environment variables
- Maintain backward compatibility with existing SSE event streams and run lifecycle
- Enable real tool execution (read/write/bash) inside Daytona sandboxes
- Support streaming responses from LLMs with incremental event delivery
- Implement proper cancellation and timeout handling through pi-agent-core
- Validate provider configuration at startup with clear error messages

**Non-Goals:**
- Multi-model routing or load balancing across providers (deferred to v1)
- Automatic provider fallback on failures
- Fine-grained model parameter exposure beyond basic configuration
- Support for non-OpenAI-compatible providers requiring custom adapters
- Real-time model switching during a run

## Decisions

**Decision 1: Use pi-agent-core's provider abstraction**
- **Rationale**: pi-agent-core already provides a clean provider interface with OpenAI and Anthropic implementations. Using this avoids reinventing provider abstractions and ensures compatibility with the agent loop framework.
- **Alternatives considered**: Building custom provider abstraction (rejected - unnecessary duplication), directly calling provider SDKs (rejected - loses pi-agent-core's streaming and tool handling benefits)

**Decision 2: Environment-based configuration with Zod validation**
- **Rationale**: Environment variables are the standard for secrets and configuration in containerized deployments. Zod provides runtime validation with excellent TypeScript integration.
- **Alternatives considered**: Config files (rejected - harder to manage secrets), database-stored config (rejected - adds complexity for v0)

**Decision 3: NestJS dependency injection for provider lifecycle**
- **Rationale**: The orchestrator is built on NestJS. Using DI allows for test mocks, clean separation of concerns, and consistent lifecycle management.
- **Alternatives considered**: Static singletons (rejected - harder to test), factory functions (rejected - less idiomatic for NestJS)

**Decision 4: Event translation layer between pi-agent-core and SSE**
- **Rationale**: pi-agent-core emits its own event types. We need to map these to our SSE event format while preserving sequence numbers and metadata.
- **Alternatives considered**: Direct passthrough (rejected - loses seq numbers and metadata), complete event redefinition (rejected - unnecessary complexity)

**Decision 5: Fail fast on invalid configuration**
- **Rationale**: Provider misconfiguration should be caught at startup, not during the first run. This provides clear error messages to operators.
- **Alternatives considered**: Lazy validation on first run (rejected - poor user experience)

## Risks / Trade-offs

**[Risk] API keys exposed in environment variables**
→ **Mitigation**: Document security best practices (secret management, .env file exclusions), validate that keys have appropriate permissions (not admin keys), consider runtime key validation without logging

**[Risk] Provider rate limits affect system availability**
→ **Mitigation**: Document rate limit behavior, implement client-visible error messages for rate limit hits, consider exponential backoff for retries (v1)

**[Risk] Real LLM latency breaks UI expectations set by scripted runtime**
→ **Mitigation**: Document expected latency, ensure streaming events provide progress feedback, test with real providers during development

**[Risk] pi-agent-core version incompatibility**
→ **Mitigation**: Pin exact version in package.json, review changelogs before updates, maintain integration tests

**[Trade-off] Testing requires real API keys**
→ Some tests will require valid API credentials and incur costs. Mark these as integration tests and provide skip flags for CI environments without keys.

## Migration Plan

**Deployment:**
1. Add provider configuration to environment (API keys, model selection)
2. Deploy new orchestrator version with real provider integration
3. Verify health check endpoint reports provider status
4. Run smoke test with simple prompt to verify end-to-end flow

**Rollback:**
- Feature flag or environment variable to fall back to scripted runtime (temporary during transition)
- Revert to previous container image if issues detected

**Open Questions**

- Should we support multiple providers simultaneously (e.g., OpenAI for some runs, Anthropic for others) or single-provider configuration?
- What is the desired behavior when provider credentials are invalid at startup - crash or degraded mode?
- Should we expose model temperature/top_p parameters as run-time options or keep them as deployment configuration?
