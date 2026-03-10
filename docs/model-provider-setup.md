# Model Provider Setup Guide

This guide walks you through configuring the Minerva orchestrator to use real LLM providers (OpenAI or Anthropic) instead of the scripted runtime.

## Quick Start

1. Choose your preferred provider: OpenAI or Anthropic
2. Obtain an API key from your chosen provider
3. Set the required environment variables
4. Verify the configuration using the health endpoint

## Configuration

### Required Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MODEL_PROVIDER` | Provider type: `openai` or `anthropic` | Yes |
| `OPENAI_API_KEY` | Your OpenAI API key (if using OpenAI) | Yes* |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (if using Anthropic) | Yes* |

*Only the API key matching your chosen provider is required.

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODEL_NAME` | Specific model to use | Provider default* |
| `MODEL_TEMPERATURE` | Sampling temperature (0-2) | Not set |
| `MODEL_MAX_TOKENS` | Maximum tokens per response | 4096 |

*OpenAI default: `gpt-4-turbo-preview`  
*Anthropic default: `claude-3-opus-20240229`

### Example Configurations

#### OpenAI Configuration
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-key-here
MODEL_NAME=gpt-4-turbo
MODEL_TEMPERATURE=0.7
MODEL_MAX_TOKENS=4096
```

#### Anthropic Configuration
```bash
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
MODEL_NAME=claude-3-opus-20240229
MODEL_TEMPERATURE=0.5
MODEL_MAX_TOKENS=8192
```

## Provider-Specific Setup

### OpenAI

1. Create an account at [OpenAI](https://openai.com/)
2. Generate an API key at [API Keys](https://platform.openai.com/api-keys)
3. Ensure your account has billing enabled
4. Note: OpenAI API keys start with `sk-`

**Available Models:**
- `gpt-4-turbo-preview` (default)
- `gpt-4`
- `gpt-3.5-turbo`
- See [OpenAI Models](https://platform.openai.com/docs/models) for full list

**Rate Limits:**
- Rate limits vary by account tier
- Check your limits at [Usage Limits](https://platform.openai.com/account/limits)

### Anthropic

1. Create an account at [Anthropic](https://www.anthropic.com/)
2. Generate an API key in the [Console](https://console.anthropic.com/)
3. Ensure your account has credits
4. Note: Anthropic API keys start with `sk-ant-`

**Available Models:**
- `claude-3-opus-20240229` (default)
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`
- See [Anthropic Models](https://docs.anthropic.com/claude/docs/models-overview) for full list

**Rate Limits:**
- Rate limits vary by account tier
- Check your limits in the console

## Verification

After setting up your configuration, verify everything is working:

```bash
# Start the orchestrator
npm run dev

# Check health endpoint
curl http://localhost:3000/health
```

Expected healthy response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "provider": {
    "type": "openai",
    "healthy": true,
    "message": "openai provider configured successfully"
  }
}
```

Unhealthy response (503 status):
```json
{
  "status": "error",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "provider": {
    "type": "openai",
    "healthy": false,
    "message": "Invalid API key format for openai"
  }
}
```

## Troubleshooting

### Configuration Errors

The application will fail fast at startup with descriptive error messages:

**Missing MODEL_PROVIDER:**
```
Model provider configuration validation failed:
MODEL_PROVIDER must be "openai" or "anthropic"
```

**Missing API Key:**
```
Model provider configuration validation failed:
OPENAI_API_KEY is required when MODEL_PROVIDER=openai
```

**Invalid API Key Format:**
```
API key format validation failed
```

### Provider Errors During Runs

Common errors and their meanings:

| Error | Cause | Solution |
|-------|-------|----------|
| "Rate limit exceeded" | Too many requests | Wait before retrying; check your rate limits |
| "Authentication failed" | Invalid API key | Verify your API key is correct and active |
| "Request timed out" | Network issues or large requests | Retry the request; check your connection |
| "API quota exceeded" | Billing limit reached | Check your billing dashboard and increase limits |

## Migration from Legacy Configuration

If you were using the old `LLM_*` variables, migrate as follows:

**Old (deprecated):**
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4
```

**New:**
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4
```

## Security Best Practices

1. **Never commit API keys** to version control
2. Use environment-specific `.env` files
3. Rotate API keys regularly
4. Use separate API keys for different environments
5. Monitor API usage for unexpected spikes
6. Set up spending limits where available

## Support

For issues related to:
- **Minerva orchestrator**: Check the [troubleshooting guide](./troubleshooting.md)
- **OpenAI API**: Visit [OpenAI Support](https://help.openai.com/)
- **Anthropic API**: Visit [Anthropic Support](https://support.anthropic.com/)
