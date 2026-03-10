## Why

Currently, the LLM configuration (base URL, API key, model) may be hardcoded or configured through other means. To improve flexibility and follow the twelve-factor app methodology, we should support configuration via standard environment variables (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL). This allows users to easily switch between different LLM providers and deployments without code changes.

## What Changes

- Add environment variable support for LLM configuration
- Support three environment variables: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Update configuration loading to read from environment
- Add validation for required environment variables
- Update documentation with new configuration options

## Capabilities

### New Capabilities
- `llm-env-config`: Support for configuring LLM connection via environment variables

### Modified Capabilities
- None (no existing spec-level behavior changes)

## Impact

- Configuration system will need to read from `process.env`
- May affect how LLM clients are instantiated
- Documentation updates required
- No breaking changes to existing APIs
