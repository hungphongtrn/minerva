# Implementation Plan: Orchestrator v0 - Project Setup

**Bean**: minerva-eegh  
**Scope**: Phase 1.1, 1.2, 1.3  
**Target**: TypeScript orchestrator service scaffolding

---

## 1. Problem Statement and Goal

### Problem
Minerva requires a foundation for building the TypeScript orchestrator service. Currently, the repository contains only documentation and research notes. We need to establish:
1. A clear repository structure for TypeScript services
2. Node.js/TypeScript project scaffolding with tooling
3. Core runtime dependencies (pi-agent-core, Daytona SDK, NestJS backend framework)

### Goal
Create a well-structured TypeScript project that serves as the foundation for:
- The orchestrator service wrapping `@mariozechner/pi-agent-core`
- Daytona sandbox integration via the TypeScript SDK
- HTTP API with Server-Sent Events (SSE) for UI streaming
- Future extensibility (tests, configs, additional packages)

---

## 2. Decision: Repository Layout

**Decision**: Single service directory with potential for future `apps/` expansion

**Rationale**:
- v0 is focused on a single orchestrator service
- Keeps initial setup simple and avoids premature abstraction
- Structure allows easy migration to `apps/` pattern later if needed

**Layout**:
```
/
├── services/                          # Service implementations
│   └── orchestrator/                  # Main orchestrator service
│       ├── package.json
│       ├── tsconfig.json
│       ├── README.md
│       ├── src/
│       │   ├── main.ts                # NestJS bootstrap entry point
│       │   ├── app.module.ts          # Root service module
│       │   ├── config/
│       │   ├── health/
│       │   ├── types/
│       │   ├── providers/
│       │   ├── services/
│       │   ├── sandbox/
│       │   ├── packs/
│       │   └── tools/
│       └── tests/
├── docs/                              # Documentation (existing)
├── package.json                       # Root workspace config (optional)
└── .gitignore                         # Root gitignore
```

---

## 3. File-Level Changes

### 3.1 New Files

#### `/services/orchestrator/package.json`
- Define project metadata, scripts, and dependencies
- Scripts: `dev`, `build`, `start`, `test`, `lint`, `format`, `typecheck`
- Engines: Node.js >= 20

#### `/services/orchestrator/tsconfig.json`
- Strict TypeScript configuration
- ES2022 target with Node.js module resolution
- Path aliases for clean imports (`@/config`, `@/services`, etc.)
- Source maps for debugging

#### `/services/orchestrator/.gitignore`
- `node_modules/`, `dist/`, `.env`, `*.log`
- IDE files (`.vscode/`, `.idea/`)
- Test coverage reports

#### `/services/orchestrator/.eslintrc.json` (or `eslint.config.mjs`)
- TypeScript ESLint recommended rules
- Import/export validation
- No `console.log` in production code (warn)

#### `/services/orchestrator/.prettierrc`
- Consistent formatting: 2-space indent, single quotes, trailing commas

#### `/services/orchestrator/src/main.ts`
- NestJS bootstrap entry point
- Creates the app, configures global concerns, and starts the HTTP server

#### `/services/orchestrator/src/app.module.ts`
- Root NestJS module wiring config, providers, and feature modules

#### `/services/orchestrator/src/health/health.controller.ts`
- Defines the `/health` endpoint inside a NestJS controller

#### `/services/orchestrator/src/health/health.module.ts`
- Groups health controller dependencies into a feature module

#### `/services/orchestrator/src/config/index.ts`
- Configuration loading (env vars, defaults)
- Type-safe config schema (Zod validation)
- Daytona SDK config, server port, logging level

#### `/services/orchestrator/src/types/index.ts`
- Core domain types shared across layers
- Re-exports from pi-agent-core types where needed

#### `/services/orchestrator/README.md`
- Service overview and setup instructions
- Development workflow
- Environment variables reference

### 3.2 Modified Files

#### `/services/orchestrator/.env.example`
- Template for required environment variables:
  ```
  PORT=3000
  NODE_ENV=development
  LOG_LEVEL=info
  DAYTONA_SERVER_URL=
  DAYTONA_API_KEY=
  DAYTONA_TARGET=
  ```

---

## 4. Key Interfaces and Types

### 4.1 Config Types

```typescript
// src/config/types.ts
export interface OrchestratorConfig {
  server: {
    port: number;
    host: string;
  };
  logging: {
    level: 'debug' | 'info' | 'warn' | 'error';
  };
  daytona: {
    serverUrl: string;
    apiKey: string;
    target: string;
  };
}
```

### 4.2 Service Layer Interfaces

```typescript
// src/services/types.ts
export interface IRunService {
  // Run lifecycle operations (to be fully defined in 2.1)
  createRun(request: CreateRunRequest): Promise<Run>;
  cancelRun(runId: string): Promise<void>;
  getRun(runId: string): Promise<Run | null>;
}

export interface ISandboxService {
  // Sandbox operations (to be fully defined in 3.1)
  createSandbox(userId: string): Promise<Sandbox>;
  executeTool(sandboxId: string, tool: ToolCall): Promise<ToolResult>;
  destroySandbox(sandboxId: string): Promise<void>;
}
```

### 4.3 Event Types (SSE Contract)

```typescript
// src/types/events.ts
export interface SSEEvent {
  id: string;
  event: string;
  data: unknown;
}

// Maps to pi-agent-core events with orchestrator additions
export type OrchestratorEvent =
  | { type: 'run_start'; runId: string; timestamp: number }
  | { type: 'run_end'; runId: string; timestamp: number; status: 'completed' | 'cancelled' | 'error' }
  | PiAgentCoreEvent; // From @mariozechner/pi-agent-core
```

### 4.4 Provider Interfaces

```typescript
// src/providers/types.ts
export interface ILogger {
  debug(message: string, meta?: Record<string, unknown>): void;
  info(message: string, meta?: Record<string, unknown>): void;
  warn(message: string, meta?: Record<string, unknown>): void;
  error(message: string, error?: Error, meta?: Record<string, unknown>): void;
}

export interface IDaytonaClient {
  createWorkspace(config: WorkspaceConfig): Promise<Workspace>;
  getWorkspace(id: string): Promise<Workspace | null>;
  executeCommand(workspaceId: string, command: string): Promise<CommandResult>;
}
```

---

## 5. Dependencies

### 5.1 Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@mariozechner/pi-agent-core` | ^latest | Agent loop and event streaming |
| `@mariozechner/pi-ai` | ^latest | AI provider abstractions |
| `@daytonaio/sdk` | ^latest | Daytona sandbox operations |
| `@nestjs/common` / `@nestjs/core` / `@nestjs/platform-express` | ^11.x | Backend service framework and HTTP platform |
| `@nestjs/config` | ^4.x | Environment/config loading for NestJS services |
| `zod` | ^3.x | Schema validation (config, API payloads) |
| `pino` | ^8.x | Structured logging |

### 5.2 Development Dependencies

| Package | Purpose |
|---------|---------|
| `typescript` | TypeScript compiler |
| `@types/node` | Node.js type definitions |
| `eslint` + `@typescript-eslint/*` | Linting |
| `prettier` | Code formatting |
| `tsx` | TypeScript execution for dev |
| `vitest` | Testing framework |
| `@types/` packages | Type definitions for dependencies |

### 5.3 Install Commands

```bash
# Navigate to service directory
cd services/orchestrator

# Runtime dependencies
npm install @mariozechner/pi-agent-core @mariozechner/pi-ai @daytonaio/sdk @nestjs/common @nestjs/core @nestjs/platform-express @nestjs/config zod pino reflect-metadata rxjs

# Dev dependencies
npm install -D typescript @types/node eslint @typescript-eslint/eslint-plugin @typescript-eslint/parser prettier tsx vitest
```

---

## 6. Test Strategy

### 6.1 Test Structure

```
services/orchestrator/
├── tests/
│   ├── unit/              # Unit tests (co-located mirror)
│   │   ├── config/
│   │   ├── services/
│   │   └── utils/
│   ├── integration/       # Integration tests
│   │   ├── api.test.ts
│   │   └── sandbox.test.ts
│   └── setup.ts           # Test utilities and fixtures
```

### 6.2 Test Types

**Unit Tests**:
- Config validation logic
- Utility functions
- Type guards and transformers
- Mock external dependencies

**Integration Tests**:
- HTTP endpoints (health check)
- Daytona SDK connection (optional, requires sandbox)
- Event stream serialization

### 6.3 Test Commands

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:unit": "vitest run --config vitest.unit.config.ts",
    "test:integration": "vitest run --config vitest.integration.config.ts"
  }
}
```

### 6.4 Coverage Targets

- Unit tests: 80% coverage for business logic
- Integration tests: Cover all HTTP endpoints
- CI gate: Tests must pass before merge

---

## 7. Dependencies on Other Sections

### 7.1 Required Before

This setup task has no upstream dependencies. It is the foundational task.

### 7.2 Enables

| Section | Task | Dependency |
|---------|------|------------|
| 2.1 | Run Service | Uses types, config, and providers defined here |
| 3.1 | Sandbox Service | Uses Daytona SDK dependency installed here |
| 4.1 | HTTP API | Uses server framework and config from this setup |
| All | Testing | Uses test framework and structure established here |

---

## 8. Development Workflow

### 8.1 Local Development

```bash
# Install dependencies
cd services/orchestrator
npm install

# Copy environment template
cp .env.example .env
# Edit .env with your values

# Run in development mode (hot reload)
npm run dev

# Type check
npm run typecheck

# Lint
npm run lint

# Format
npm run format

# Run tests
npm run test
```

### 8.2 Build and Start

```bash
# Production build
npm run build

# Start production server
npm start
```

---

## 9. Acceptance Criteria

- [ ] `npm install` completes without errors
- [ ] `npm run typecheck` passes with strict settings
- [ ] `npm run lint` passes with zero errors
- [ ] `npm run test` passes (at minimum, a placeholder test)
- [ ] `npm run dev` starts the server on configured port
- [ ] `/health` endpoint returns 200 OK
- [ ] All dependencies from 1.3 are installed and importable
- [ ] README documents setup and development workflow

---

## 10. Reference Links

### Project Documentation
- [Project Scope](../../../docs/PROJECT.md) - What Minerva is building
- [Coding Standards](../../../docs/CODING_STANDARDS.md) - Quality and architecture rules
- [Architecture Notes](../../../docs/architecture/agent-runtime-v0.md) - Orchestrator + sandbox design

### Research and Design
- [Process Workflow](../../../docs/process/markdown-beans-workflow.md) - Markdown-first planning and bean tracking expectations
- [Project Scope](../../../docs/PROJECT.md) - Goals, constraints, and non-goals for the MVP
- [Architecture Notes](../../../docs/architecture/agent-runtime-v0.md) - Runtime design context
- [pi-agent-core Events](../../../docs/research/pi-agent-core/events.md) - Event streaming reference

### External Dependencies
- [@mariozechner/pi-agent-core](https://www.npmjs.com/package/@mariozechner/pi-agent-core)
- [@daytonaio/sdk](https://www.npmjs.com/package/@daytonaio/sdk)
- [NestJS](https://nestjs.com/) - backend application framework
- [Zod](https://zod.dev/) - Schema validation
- [Vitest](https://vitest.dev/) - Testing framework

---

## 11. Notes and Risks

### Risk: Package Availability
The `@mariozechner/pi-agent-core` and `@mariozechner/pi-ai` packages may be private or scoped. Verify access or use placeholder imports if unavailable during initial setup.

**Mitigation**: 
- Add placeholder type definitions if packages are unavailable
- Document how to obtain access to private packages
- Consider npm registry configuration

### Risk: Node.js Version
pi-agent-core requires Node.js >= 20.

**Mitigation**: Document requirement in README and add `.nvmrc` file.

### Risk: Daytona SDK Compatibility
Ensure Daytona TS SDK version is compatible with orchestrator Node.js version.

**Mitigation**: Pin to known working versions in package.json.

---

## 12. Post-Setup Verification

After completing this plan, verify:

1. Directory structure matches specification
2. All config files are valid JSON/TypeScript
3. `npm run typecheck` completes without errors
4. Can import all required dependencies:
   ```typescript
   import { Agent } from '@mariozechner/pi-agent-core';
   import { Daytona } from '@daytonaio/sdk';
   import { NestFactory } from '@nestjs/core';
   ```
5. Server starts and responds to health check
6. Test suite runs (even if empty)

---

*Plan created: 2025-03-09*  
*Status: Ready for implementation*
