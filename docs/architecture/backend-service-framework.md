# Backend Service Framework

Minerva standardizes long-lived TypeScript backend services on NestJS.

## Decision

- Use NestJS for deployable backend services such as `services/orchestrator`.
- Prefer Nest modules, controllers, and dependency injection over ad hoc HTTP bootstraps.
- Keep framework-specific code near the service edge; keep domain logic in focused services and types.

## Why NestJS

- Consistent service structure makes the repo easier to navigate as more services are added.
- Dependency injection gives clear seams for Daytona, persistence, streaming, and future provider adapters.
- Nest testing utilities make controller and integration tests uniform.
- Cross-cutting concerns such as config, logging, guards, interceptors, and exception filters have first-class patterns.
- The orchestrator is expected to grow beyond a single health route, so a batteries-included service framework is worth the extra weight.

## Scope

- This decision applies to backend services in `services/`.
- Small one-off scripts, CLIs, and local tooling do not need NestJS.
- Shared domain packages should remain framework-light when possible.

## Orchestrator Implications

- `services/orchestrator/src/main.ts` is the Nest bootstrap entry point.
- HTTP endpoints should live in feature folders with `*.controller.ts`, `*.module.ts`, and focused providers.
- Existing run-management logic can stay framework-agnostic and be injected into controllers/modules over time.

## Related Docs

- `docs/PROJECT.md`
- `docs/rulebooks/coding-standards.md`
- `docs/architecture/agent-runtime-v0.md`
