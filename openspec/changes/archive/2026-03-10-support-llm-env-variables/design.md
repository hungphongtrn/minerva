## Context

The Minerva agent runtime needs to support flexible LLM configuration. Currently, LLM settings may be hardcoded or configured through other mechanisms. This design adds support for standard environment variable configuration, following twelve-factor app principles.

## Goals / Non-Goals

**Goals:**
- Support `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` environment variables
- Validate environment variables at startup
- Provide clear error messages for missing configuration
- Ensure configuration is available throughout the NestJS application

**Non-Goals:**
- Support for configuration files (JSON, YAML, etc.)
- Hot-reloading of configuration
- Multiple LLM provider fallback chains
- Secrets management integration (Vault, AWS Secrets Manager, etc.)

## Decisions

**1. Use NestJS ConfigModule for environment variable handling**
- Rationale: Standard NestJS pattern, provides validation, caching, and type safety
- Alternative considered: Direct `process.env` access - rejected due to lack of validation and type safety

**2. Create a dedicated LLM configuration module**
- Rationale: Isolates LLM-specific configuration logic, enables dependency injection
- Alternative considered: Inline configuration in existing modules - rejected to maintain separation of concerns

**3. Validate at application startup (fail-fast)**
- Rationale: Catch configuration errors immediately rather than at runtime during LLM calls
- Alternative considered: Lazy validation - rejected as it defers error detection

**4. Use Joi or class-validator for validation**
- Rationale: Provides declarative validation rules and clear error messages
- Alternative considered: Manual validation - rejected for maintainability

**5. Integrate with pi-mono's ai package**
- Rationale: The project will use `@mariozechner/ai` from pi-mono (https://github.com/badlogic/pi-mono/tree/main/packages/ai) for LLM interactions
- The pi-mono package uses provider-specific env vars (OPENAI_API_KEY, etc.) by default
- We will bridge generic LLM_* variables to the package by:
  - Creating a custom Model with `baseUrl` from LLM_BASE_URL
  - Passing `apiKey` explicitly from LLM_API_KEY in options
  - Using LLM_MODEL as the model identifier

## Risks / Trade-offs

- **[Risk]** Environment variables may contain secrets that could be logged accidentally
  → **Mitigation**: Never log LLM_API_KEY, mark config fields with `@Exclude()` if using class-transformer

- **[Risk]** No support for multiple LLM providers simultaneously
  → **Mitigation**: Documented as non-goal; future enhancement could add provider-specific prefixes

- **[Trade-off]** Startup fails if env vars are missing
  → **Acceptance**: Fail-fast is preferred over runtime failures
