---
# minerva-ix5z
title: Produce layer 1 design docs for minerva-qqaa
status: completed
type: task
priority: normal
created_at: 2026-03-12T06:16:48Z
updated_at: 2026-03-12T06:25:22Z
parent: minerva-qqaa
---

## Goal
Create the architecture/design documentation layer for minerva-qqaa before implementation planning.

## Scope
- Compare current Minerva orchestrator flow to the pi coding agent reference
- Design Postgres-backed session persistence for pi-compatible durable behavior
- Design the Minerva session runtime adapter for pi coding agent semantics
- Design the Daytona-backed coding tool adapter
- Design sandbox workspace/resource loading behavior for AGENTS.md, skills, and related files
- Define HTTP/SSE contract updates for consumer-safe pi-like runtime behavior
- Design export compatibility for pi-shaped session artifacts

## Deliverables
- Focused docs under docs/ following progressive disclosure
- Updated docs indexes and decision log entries as needed
- A design baseline suitable for later implementation planning

## Checklist
- [x] Create docs/discussions or architecture references for the layer 1 scope
- [x] Compare current orchestrator flow to pi coding agent reference
- [x] Propose Postgres-backed session persistence design
- [x] Define Daytona execution adapter expectations
- [x] Define resource-loading and workspace layout behavior
- [x] Define HTTP/SSE and export compatibility expectations
- [x] Link resulting docs back to minerva-qqaa and prepare for layer 2 planning

## Summary of Changes

- Added a new `docs/architecture/minerva-qqaa/` layer-1 design set with focused notes for runtime comparison, Postgres session persistence, Daytona/runtime adapters, and HTTP/SSE plus export compatibility.
- Updated `docs/architecture/INDEX.md`, `docs/INDEX.md`, and `docs/DECISIONS.md` so the new design baseline is indexed and recorded.
- Captured layer-2 planning inputs for schema, adapter boundaries, replay semantics, and migration from the current run-centric orchestrator flow.
