# Minerva QQAA Layer 1 Design Index

Layer 1 design notes for `minerva-qqaa` and child bean `minerva-ix5z`.

These docs establish the pre-implementation architecture baseline for aligning Minerva with pi coding agent SDK semantics while preserving Minerva's hosted, multi-tenant deployment model.

## Related references

- Bean: [`minerva-qqaa`](../../../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)
- Bean: [`minerva-ix5z`](../../../.beans/minerva-ix5z--produce-layer-1-design-docs-for-minerva-qqaa.md)
- Discussion record: [`docs/disussions/minerva-qqaa-pi-coding-agent-alignment.md`](../../disussions/minerva-qqaa-pi-coding-agent-alignment.md)
- Research: [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)
- Research: [`docs/research/pi-agent-core/sessions.md`](../../research/pi-agent-core/sessions.md)

## Documents

- [`current-vs-pi-runtime.md`](./current-vs-pi-runtime.md): compares the current orchestrator flow with pi coding agent expectations and identifies the main gaps.
- [`session-persistence.md`](./session-persistence.md): Postgres-backed session persistence design, durable record boundaries, and replay/export model.
- [`runtime-and-sandbox-adapters.md`](./runtime-and-sandbox-adapters.md): session runtime adapter, Daytona tool execution adapter, workspace lifecycle, and resource-loading behavior.
- [`api-and-export-compatibility.md`](./api-and-export-compatibility.md): HTTP/SSE contract updates, consumer-safe behavior, and pi-shaped export compatibility.

## Layer 1 outcomes

This layer establishes:

- the target runtime shape
- the durable session data model
- the sandbox and resource-loading model
- the API compatibility direction
- the implementation-planning questions that belong in layer 2

## Layer 2 planning inputs

The next planning layer should turn this baseline into:

- concrete Postgres schema migrations and repository interfaces
- runtime service/module boundaries and dependency graph
- exact API payload definitions and replay semantics
- sandbox lifecycle state machines and failure handling
- phased implementation beans linked back to `minerva-qqaa`
