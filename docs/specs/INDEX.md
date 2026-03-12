# Technical Reference Docs

Plain-markdown technical reference documents for Minerva's core subsystems. These docs are maintained directly in-repo and do not depend on specification plugins.

## Specifications

### Agent Packs
- `docs/specs/agent-packs.md`: Agent pack format, AGENTS.md structure, and skill loading behavior.

### Event Streaming
- `docs/specs/event-streaming.md`: SSE endpoint behavior, event schema, and streaming lifecycle.

### Run Orchestration
- `docs/specs/run-orchestration.md`: Run lifecycle, queuing, cancellation, timeouts, and disconnect handling.

### Sandbox Execution
- `docs/specs/sandbox-execution.md`: Daytona sandbox integration, tool surface, and security constraints.

## Document Format

Each technical reference doc should stay in plain markdown and use only the structure needed for the topic. Common sections include:

- **Purpose**: overview of the subsystem or document intent
- **Requirements or Rules**: behavioral expectations when needed
- **Scenarios or Examples**: concrete illustrations
- **Links**: related architecture, research, plan, or bean artifacts

Use RFC 2119 language only when it improves clarity. The repository does not require any external specification plugin or schema.
