# Coding Standards

This document defines code quality, modularity, and architecture dependency rules for Minerva.

## Core Quality Principles

- Keep modules focused and cohesive (single responsibility per file/module).
- Keep code files small and readable; target **<500 LoC per code file**.
- If a file grows near the limit, split by concern (domain/service/adapter/util).
- Avoid "god" files/classes that mix API, orchestration, data access, and formatting logic.
- Favor explicit typed interfaces and clear boundaries between layers.
- Keep functions short and intention-revealing; extract non-trivial logic into named helpers.
- Add comments only for non-obvious constraints, trade-offs, or invariants.

## Backend Service Standard

- Use NestJS for deployable TypeScript backend services in `services/` unless a documented exception is approved.
- Organize backend code by feature modules first, then supporting providers/config/types.
- Keep controllers thin; put orchestration and domain behavior in injectable services.
- Use Nest testing utilities for controller/module coverage and keep e2e checks around public HTTP contracts.

## Harness-Oriented Engineering

Inspired by OpenAI Harness Engineering practices:

- Keep intent legible in-repo: specs/docs/tasks are the source of truth.
- Prefer deterministic contracts: schemas, event envelopes, stable API shapes.
- Define mechanical checks for meaningful changes: typecheck, lint, unit/integration tests.
- Instrument critical flows for diagnosis (run IDs, structured logs, consistent error surfaces).
- Ship in small, verifiable increments to keep feedback loops fast.

## Architecture Dependency Rules

Canonical rule:

- Within each business domain (for example, App Settings), code can only depend **forward** through this fixed layer chain:
  `Types -> Config -> Repo -> Service -> Runtime -> UI`
- Cross-cutting concerns (auth, connectors, telemetry, feature flags) must enter through one explicit interface layer: `Providers`.
- Any dependency outside these allowed edges is disallowed and should be enforced mechanically.

Reference dependency model:

```text
       +-----------+
       |   Utils   |
       +-----+-----+
             |
             v
+-------------------------------------------------------+
|                 Business logic domain                 |
|                                                       |
|  +-----------+          +--------------------------+  |
|  | Providers +---------->|      App Wiring + UI    |  |
|  +-----+-----+          +------------^-------------+  |
|        |                             |                |
|        v                +------------+-----+    +----+|
|  +-----------+          |                  |    |    ||
|  |  Service  +---------->      Runtime     +----> UI ||
|  +-----^-----+          |                  |    |    ||
|        |                +------------------+    +----+|
|        |                                              |
|  +-----+-----+          +------------+          +----+|
|  |   Types   +---------->   Config   +---------->Repo||
|  +-----------+          +------------+          +----+|
|                                                       |
+-------------------------------------------------------+
```

Allowed dependency edges (strict):

- `types -> config`
- `config -> repo`
- `repo -> service`
- `service -> runtime`
- `runtime -> ui`
- `providers -> (domain via explicit provider interfaces only)`

Constraints:

- No reverse edges (for example, `service -> repo` is disallowed if not part of the forward chain definition).
- No layer skipping (for example, `config -> service` or `types -> repo` are disallowed).
- No lateral imports between sibling modules in the same layer unless explicitly approved.
- Keep domain logic in `service`; keep IO and external integrations behind `providers` and `repo` boundaries.
- Enforce with tooling when possible (import-lint rules, path alias boundaries, CI checks).

## Testing Expectations

- Co-locate tests with modules or use mirrored test structure.
- Add unit tests for service/domain logic and integration tests for runtime/provider boundaries.
- For orchestrator/event changes, include event ordering and cancellation-path coverage.
