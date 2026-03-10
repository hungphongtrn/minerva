# Minerva Orchestrator Service

The orchestrator service manages agent runs and Daytona sandbox environments for Minerva.

## Overview

This service provides:
- NestJS HTTP API with a stable module/controller/provider structure
- HTTP API with Server-Sent Events (SSE) for UI streaming
- Integration with `@mariozechner/pi-agent-core` for agent loop and event streaming
- Daytona sandbox management via the TypeScript SDK
- Type-safe configuration and logging

## Prerequisites

- Node.js >= 20.0.0 (see `.nvmrc`)
- npm
- Access to Daytona server (for sandbox features)

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

3. **Environment Variables:**
   | Variable | Description | Default |
   |----------|-------------|---------|
   | `PORT` | HTTP server port | 3000 |
   | `NODE_ENV` | Environment mode | development |
   | `LOG_LEVEL` | Logging level | info |
   | `DAYTONA_SERVER_URL` | Daytona server URL | - |
   | `DAYTONA_API_KEY` | Daytona API key | - |
   | `DAYTONA_TARGET` | Daytona target region | us |
   | `LLM_BASE_URL` | LLM API base URL | - |
   | `LLM_API_KEY` | LLM API key | - |
   | `LLM_MODEL` | LLM model identifier | - |

## Development

```bash
# Start development server (hot reload)
npm run dev

# Type check
npm run typecheck

# Lint
npm run lint

# Format code
npm run format

# Run tests
npm run test
```

## Production

```bash
# Build
npm run build

# Start
npm start
```

## API Endpoints

- `GET /health` - Health check endpoint

## LLM Configuration

The orchestrator supports LLM configuration via environment variables following the twelve-factor app methodology. All LLM configuration is validated at startup with fail-fast behavior.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_BASE_URL` | Base URL of the LLM API endpoint | `https://api.openai.com/v1` |
| `LLM_API_KEY` | API key for LLM authentication | `sk-...` |
| `LLM_MODEL` | Model identifier | `gpt-4`, `gpt-3.5-turbo` |

### Example Configurations

**OpenAI:**
```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-4
```

**Local/Self-hosted (e.g., Ollama, LocalAI):**
```bash
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=your-local-key
LLM_MODEL=llama-2-70b
```

**Custom Provider:**
```bash
LLM_BASE_URL=https://api.custom-provider.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=custom-model
```

### Validation

All three variables are required. The application will fail to start with a clear error message if any are missing or invalid:

- `LLM_BASE_URL` must be a valid HTTP/HTTPS URL
- `LLM_API_KEY` must be a non-empty string
- `LLM_MODEL` must be a non-empty string

### Security Notes

- The `LLM_API_KEY` is never logged
- The API key is only accessed via the `LlmConfig.getApiKey()` method
- When using the `@mariozechner/pi-ai` package, always pass the API key explicitly via the `apiKey` option

### Error Messages and Troubleshooting

**Error: "LLM configuration validation failed: LLM_BASE_URL: Required"**
- The `LLM_BASE_URL` environment variable is missing
- Solution: Set `LLM_BASE_URL` in your `.env` file or environment

**Error: "LLM configuration validation failed: LLM_BASE_URL: Invalid url"**
- The provided URL is not a valid HTTP/HTTPS URL
- Solution: Ensure the URL starts with `http://` or `https://` and is properly formatted

**Error: "LLM configuration validation failed: LLM_API_KEY: String must contain at least 1 character(s)"**
- The `LLM_API_KEY` is empty or missing
- Solution: Set a valid API key

**Error: "LLM configuration validation failed: LLM_MODEL: String must contain at least 1 character(s)"**
- The `LLM_MODEL` is empty or missing
- Solution: Set a valid model identifier

## Architecture

```
src/
├── app.module.ts  # Root NestJS module
├── main.ts        # NestJS bootstrap entry point
├── config/        # Configuration loading and DI provider
├── health/        # Health controller module
├── providers/     # External service providers (logging, Daytona)
├── services/      # Business logic services
└── types/         # Shared domain types
```

## Repository Layout

See `REPOSITORY_LAYOUT.md` for the full repository structure.
