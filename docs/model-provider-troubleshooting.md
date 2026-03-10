# Troubleshooting Model Provider Issues

This guide helps you diagnose and resolve common issues with the model provider integration.

## Startup Failures

### "MODEL_PROVIDER must be 'openai' or 'anthropic'"

**Problem:** The `MODEL_PROVIDER` environment variable is missing or invalid.

**Solution:**
```bash
# Set the provider in your .env file
MODEL_PROVIDER=openai  # or anthropic
```

### "OPENAI_API_KEY is required when MODEL_PROVIDER=openai"

**Problem:** You've selected OpenAI as the provider but haven't provided an API key.

**Solution:**
1. Get an API key from [OpenAI](https://platform.openai.com/api-keys)
2. Add it to your `.env` file:
```bash
OPENAI_API_KEY=sk-your-key-here
```

### "ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic"

**Problem:** You've selected Anthropic as the provider but haven't provided an API key.

**Solution:**
1. Get an API key from [Anthropic Console](https://console.anthropic.com/)
2. Add it to your `.env` file:
```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## Health Check Failures

### Health endpoint returns 503 with "Invalid API key format"

**Problem:** The API key doesn't match the expected format for the provider.

**Solution:**
- OpenAI keys should start with `sk-`
- Anthropic keys should start with `sk-ant-`

Verify your key format:
```bash
# OpenAI
echo $OPENAI_API_KEY | grep "^sk-"

# Anthropic
echo $ANTHROPIC_API_KEY | grep "^sk-ant-"
```

### Health endpoint returns 503 with "Provider unhealthy"

**Problem:** The provider service cannot validate the configuration.

**Solution:**
1. Check that your API key is active and hasn't been revoked
2. Verify you have sufficient credits/quota
3. Check provider status pages:
   - [OpenAI Status](https://status.openai.com/)
   - [Anthropic Status](https://status.anthropic.com/)

## Runtime Errors

### "Rate limit exceeded" during run execution

**Problem:** You've hit the provider's rate limit.

**Symptoms:**
- Run fails with error message mentioning "rate limit" or "429"
- Multiple runs failing in quick succession

**Solution:**
1. Reduce the frequency of requests
2. Implement retry logic with exponential backoff
3. Upgrade your provider plan for higher limits
4. Monitor your usage in the provider dashboard

### "Authentication failed" during run execution

**Problem:** The API key is invalid or has been revoked.

**Symptoms:**
- Run fails immediately with auth error
- Error mentions "unauthorized" or "401"

**Solution:**
1. Verify the API key is correct
2. Check if the key was revoked in the provider dashboard
3. Generate a new API key if needed
4. Update your `.env` file with the new key

### "Request timed out" during run execution

**Problem:** The LLM request took too long to respond.

**Symptoms:**
- Run hangs for a while then fails
- Error mentions "timeout" or "ETIMEDOUT"

**Solution:**
1. Check your network connection
2. Reduce `MODEL_MAX_TOKENS` for faster responses
3. Check provider status for outages
4. Try again later if the provider is experiencing high load

### "API quota exceeded" during run execution

**Problem:** You've exceeded your billing quota or spending limit.

**Symptoms:**
- Error mentions "quota", "billing", or "exceeded"

**Solution:**
1. Check your usage and billing in the provider dashboard
2. Increase your spending limit if needed
3. Add credits to your account
4. Contact provider support if you believe this is an error

## Configuration Issues

### Model not available

**Problem:** The specified model name doesn't exist or isn't available for your account.

**Symptoms:**
- Error mentions "model not found" or invalid model ID

**Solution:**
1. Check the correct model ID from the provider documentation
2. Ensure the model is available for your account tier
3. Use a default model if unsure:
   - OpenAI: `gpt-4-turbo-preview`
   - Anthropic: `claude-3-opus-20240229`

### Temperature out of range

**Problem:** The `MODEL_TEMPERATURE` value is invalid.

**Solution:**
Temperature must be between 0 and 2:
```bash
MODEL_TEMPERATURE=0.7  # Valid
MODEL_TEMPERATURE=-0.5 # Invalid
MODEL_TEMPERATURE=3.0  # Invalid
```

### Max tokens invalid

**Problem:** The `MODEL_MAX_TOKENS` value is invalid.

**Solution:**
Max tokens must be a positive integer:
```bash
MODEL_MAX_TOKENS=4096   # Valid
MODEL_MAX_TOKENS=-100   # Invalid
MODEL_MAX_TOKENS=0      # Invalid
```

## Development Issues

### Tests fail with "Provider configuration validation failed"

**Problem:** Test environment doesn't have the required configuration.

**Solution:**
Set up test environment variables or mock the provider:
```bash
# In test environment
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-test-key
```

Or use the provided mocks in unit tests.

### Build errors related to ModelProvider

**Problem:** TypeScript compilation errors.

**Solution:**
1. Run the build to see specific errors:
   ```bash
   npm run build
   ```
2. Ensure all dependencies are installed:
   ```bash
   npm install
   ```
3. Check that you're importing from the correct paths

## Debugging Tips

### Enable Debug Logging

Set the log level to debug for more detailed output:
```bash
LOG_LEVEL=debug
```

This will show:
- Provider initialization details
- Stream creation events
- Health check results

### Check Environment Variables

Verify your environment variables are loaded correctly:
```bash
# Print all MODEL_ variables
env | grep MODEL_
```

### Test Provider Connectivity

Use the health endpoint to test connectivity:
```bash
curl -v http://localhost:3000/health
```

Look for:
- HTTP 200: Provider is healthy
- HTTP 503: Provider is unhealthy (check response body for details)

### Verify API Key Permissions

Test your API key directly with the provider:

**OpenAI:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Anthropic:**
```bash
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

## Getting Help

If you're still experiencing issues:

1. Check the [Model Provider Setup Guide](./model-provider-setup.md) for configuration details
2. Review the [Coding Standards](../CODING_STANDARDS.md) for implementation details
3. Check provider-specific documentation:
   - [OpenAI API Docs](https://platform.openai.com/docs)
   - [Anthropic API Docs](https://docs.anthropic.com/claude/reference)
4. File an issue in the repository with:
   - Error messages (redact API keys!)
   - Configuration (without sensitive data)
   - Steps to reproduce
