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
