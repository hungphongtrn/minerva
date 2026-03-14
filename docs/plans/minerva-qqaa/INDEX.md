# Minerva QQAA Plans Index

Proposal and implementation-planning artifacts for `minerva-qqaa`.

These docs are disposable/supporting artifacts. They capture the unapproved `minerva-qqaa` proposal and its implementation planning, while canonical ground truth stays unchanged until the direction is finalized and approved.

## Related references

- Bean: [`minerva-qqaa`](../../../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)
- Bean: [`minerva-03i3`](../../../.beans/minerva-03i3--produce-layer-2-implementation-planning-for-minerv.md)
- Bean: [`minerva-jrub`](../../../.beans/minerva-jrub--reclassify-unapproved-minerva-qqaa-architecture-do.md)
- Canonical status note: [`docs/architecture/minerva-qqaa/INDEX.md`](../../architecture/minerva-qqaa/INDEX.md)
- Discussion record: [`docs/disussions/minerva-qqaa-pi-coding-agent-alignment.md`](../../disussions/minerva-qqaa-pi-coding-agent-alignment.md)
- Research: [`docs/research/pi-coding-agent-sdk.md`](../../research/pi-coding-agent-sdk.md)

## Documents

- [`current-vs-pi-runtime.md`](./current-vs-pi-runtime.md): layer-1 proposal comparing the current orchestrator flow with pi coding agent expectations and identifying the main gaps.
- [`session-persistence.md`](./session-persistence.md): layer-1 proposal for Postgres-backed session persistence, durable record boundaries, and replay/export behavior.
- [`runtime-and-sandbox-adapters.md`](./runtime-and-sandbox-adapters.md): layer-1 proposal for the hosted session runtime adapter, Daytona execution boundary, workspace lifecycle, and runtime resource materialization.
- [`api-and-export-compatibility.md`](./api-and-export-compatibility.md): layer-1 proposal for session-aware HTTP/SSE contracts, consumer-safe behavior, and pi-shaped export compatibility.
- [`layer-2-implementation-plan.md`](./layer-2-implementation-plan.md): implementation-ready plan covering schema evolution, repository boundaries, runtime services, sandbox/resource materialization, API changes, export strategy, and phased delivery slices.
