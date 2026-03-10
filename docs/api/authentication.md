# API Authentication

## Overview

Minerva Orchestrator v0 uses API key authentication for all endpoints. Each request must include a valid API key in the Authorization header.

## Authentication Method

### API Key Header

Include the API key in the `Authorization` header using the `Bearer` scheme:

```http
Authorization: Bearer {api_key}
```

### Example Request

```bash
curl http://localhost:3000/api/v0/runs \
  -H "Authorization: Bearer minerva_api_key_123"
```

## API Key Format

API keys follow the format:

```
minerva_{identifier}_{random_segment}
```

Example:
```
minerva_prod_a1b2c3d4e5f6
```

## Configuration

### Environment Variables

Set the API key via environment variable:

```bash
export MINERVA_API_KEY=minerva_api_key_123
```

### Server Configuration

The server validates API keys against configured allowed keys:

```typescript
// config/index.ts
export const config = {
  apiKeys: [
    'minerva_prod_a1b2c3d4e5f6',
    'minerva_test_x7y8z9w0v1',
  ],
};
```

## Error Responses

### Missing API Key

**401 Unauthorized**

```json
{
  "error": "UNAUTHORIZED",
  "message": "API key is required",
  "code": "AUTH_REQUIRED"
}
```

### Invalid API Key

**401 Unauthorized**

```json
{
  "error": "UNAUTHORIZED",
  "message": "Invalid API key",
  "code": "INVALID_API_KEY"
}
```

### Expired API Key

**401 Unauthorized**

```json
{
  "error": "UNAUTHORIZED",
  "message": "API key has expired",
  "code": "API_KEY_EXPIRED"
}
```

## Security Best Practices

### API Key Management

1. **Store securely**: Never commit API keys to version control
2. **Rotate regularly**: Change keys every 90 days
3. **Use environment variables**: Keep keys out of code
4. **Limit scope**: Use different keys for different environments
5. **Monitor usage**: Track API key usage for anomalies

### Production Deployment

```bash
# Production
MINERVA_API_KEY=minerva_prod_$(openssl rand -hex 16)

# Development
MINERVA_API_KEY=minerva_dev_test_key
```

### Rate Limiting

API keys may be subject to rate limiting:

| Tier | Requests/minute | Concurrent runs |
|------|----------------|-----------------|
| Free | 60 | 1 |
| Pro | 600 | 5 |
| Enterprise | 6000 | Unlimited |

Rate limit headers are included in responses:

```http
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 599
X-RateLimit-Reset: 1640995200
```

## Future Enhancements

Planned authentication improvements:

- **OAuth 2.0**: Integration with identity providers
- **JWT Tokens**: Short-lived access tokens
- **Scoped Keys**: Fine-grained permissions per key
- **Audit Logging**: Track all authentication attempts
- **IP Whitelisting**: Restrict key usage by IP address
