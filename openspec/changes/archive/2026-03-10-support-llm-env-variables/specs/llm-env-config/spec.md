## ADDED Requirements

### Requirement: Environment variables are loaded at startup
The system SHALL read LLM configuration from environment variables at application startup.

#### Scenario: All required variables are present
- **WHEN** the application starts with `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` set
- **THEN** the application initializes successfully with the provided configuration

#### Scenario: Required variables are missing
- **WHEN** the application starts without one or more required environment variables
- **THEN** the application SHALL fail to start with a clear error message indicating which variables are missing

### Requirement: LLM_BASE_URL is a valid URL
The system SHALL validate that `LLM_BASE_URL` is a valid HTTP/HTTPS URL.

#### Scenario: Valid URL provided
- **WHEN** `LLM_BASE_URL` is set to "https://api.openai.com/v1"
- **THEN** the system accepts the URL as valid

#### Scenario: Invalid URL provided
- **WHEN** `LLM_BASE_URL` is set to "not-a-valid-url"
- **THEN** the system SHALL reject the configuration with an error message

### Requirement: LLM_API_KEY is non-empty
The system SHALL validate that `LLM_API_KEY` is a non-empty string.

#### Scenario: Valid API key provided
- **WHEN** `LLM_API_KEY` is set to a non-empty string
- **THEN** the system accepts the API key as valid

#### Scenario: Empty API key provided
- **WHEN** `LLM_API_KEY` is set to an empty string
- **THEN** the system SHALL reject the configuration with an error message

### Requirement: LLM_MODEL is non-empty
The system SHALL validate that `LLM_MODEL` is a non-empty string.

#### Scenario: Valid model provided
- **WHEN** `LLM_MODEL` is set to "gpt-4" or any non-empty string
- **THEN** the system accepts the model as valid

#### Scenario: Empty model provided
- **WHEN** `LLM_MODEL` is set to an empty string
- **THEN** the system SHALL reject the configuration with an error message

### Requirement: Configuration is accessible via dependency injection
The system SHALL expose the LLM configuration through NestJS dependency injection.

#### Scenario: Service requires LLM configuration
- **WHEN** a service injects the LLM configuration
- **THEN** the service receives the configuration values from environment variables

### Requirement: Configuration creates pi-mono compatible custom model
The system SHALL create a custom Model object compatible with `@mariozechner/ai` package using the generic LLM_* environment variables.

#### Scenario: Creating custom model from environment variables
- **WHEN** the system reads `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` from environment
- **THEN** it SHALL create a Model object with:
  - `baseUrl` set to LLM_BASE_URL
  - `id` set to LLM_MODEL
  - `api` set to 'openai-completions' (OpenAI-compatible API)

#### Scenario: Using configuration with pi-mono package
- **WHEN** calling `stream()` or `complete()` with the custom model
- **THEN** the system SHALL pass `LLM_API_KEY` explicitly in the options parameter
- **AND** the pi-mono package SHALL use these values instead of provider-specific environment variables
