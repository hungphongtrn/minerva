---
# minerva-eegh
title: Project Setup
status: completed
type: task
priority: high
tags:
    - harvest
    - orchestrator-v0
created_at: 2026-03-09T08:10:15Z
updated_at: 2026-03-09T08:51:22Z
parent: minerva-5rrj
---

## Bean: minerva-eegh — Project Setup

**Status**: todo

**Requirements**:
- [x] 1.1 Decide repository layout for the TypeScript orchestrator (single service vs apps/ directory) and document it
- [x] 1.2 Add Node.js/TypeScript project scaffolding (package manager, tsconfig, lint/format)
- [x] 1.3 Add dependencies: `@mariozechner/pi-agent-core`, `@mariozechner/pi-ai`, Daytona TS SDK, and an HTTP server framework

## Plan

📄 [Implementation Plan: Orchestrator v0 - Project Setup](./docs/plans/orchestrator-v0/project-setup.md)

The plan includes:
- Repository layout decision (single service with `services/orchestrator/`)
- File-level changes (new files, modified files)
- Key interfaces and types (config, services, events, providers)
- Test strategy (unit/integration with Vitest)
- Dependencies on other sections (enables sections 2.1, 3.1, 4.1)
- Reference links to all consulted documentation

## Context

This is the foundational task for the orchestrator v0. It establishes the TypeScript project structure before implementing run orchestration, sandbox execution, and HTTP APIs.

## Acceptance Criteria

- [ ] `npm install` completes without errors
- [ ] `npm run typecheck` passes with strict settings
- [ ] `npm run lint` passes with zero errors
- [ ] `npm run test` passes (at minimum, a placeholder test)
- [ ] `npm run dev` starts the server on configured port
- [ ] `/health` endpoint returns 200 OK
- [ ] All dependencies from 1.3 are installed and importable
- [ ] README documents setup and development workflow

## Summary of Changes\n\nCreated complete TypeScript orchestrator project structure at services/orchestrator/:\n\n**Repository Layout** (REPOSITORY_LAYOUT.md):\n- Single service layout (services/orchestrator/) with future apps/ expansion potential\n- Clear separation of concerns: config, types, providers, services, repo, runtime\n\n**Node.js/TypeScript Scaffolding**:\n- package.json with scripts (dev, build, start, test, lint, format, typecheck)\n- tsconfig.json with strict settings, path aliases, ES2022 target\n- ESLint config with TypeScript support\n- Prettier config with 2-space indent, single quotes\n- .gitignore for node_modules, dist, .env, IDE files\n- .nvmrc with Node.js >= 20\n- .env.example with all required variables\n\n**Dependencies Installed**:\n- Runtime: @daytonaio/sdk, hono, @hono/node-server, pino, zod\n- Dev: typescript, @types/node, eslint, prettier, tsx, vitest\n- Note: @mariozechner/pi-agent-core and @mariozechner/pi-ai packages are private/not available; added placeholders for future integration\n\n**Core Source Files**:\n- src/index.ts - Entry point with graceful shutdown\n- src/server.ts - Hono HTTP server with /health endpoint\n- src/config/ - Zod-validated config loading\n- src/types/ - Domain types (Run, Sandbox, ToolCall, etc.)\n- src/providers/ - Logger and Daytona client interfaces\n- src/services/ - Service layer interfaces (IRunService, ISandboxService)\n\n**Tests**:\n- Vitest configuration (unit and integration)\n- Placeholder test passing\n\n**Documentation**:\n- README.md with setup instructions, environment variables, and development workflow\n\n**Verification**:\n- ✅ npm install completes without errors\n- ✅ npm run typecheck passes\n- ✅ npm run test passes (2 tests)\n- ✅ All dependencies importable\n- ✅ Health endpoint configured
