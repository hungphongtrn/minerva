---
# minerva-yaz0
title: Migrate orchestrator from Hono to NestJS
status: completed
type: task
created_at: 2026-03-09T09:26:19Z
updated_at: 2026-03-09T09:26:19Z
parent: minerva-5rrj
---

Replace Hono usage in services/orchestrator with NestJS and update docs to reflect the architectural decision.

- [x] Find all Hono references in the repo
- [x] Refactor services/orchestrator to use NestJS bootstrap, modules, controllers, and providers
- [x] Update tests and package configuration for NestJS
- [x] Update docs in docs/ and service docs to justify NestJS as the standard

## Summary of Changes

Migrated the orchestrator service from a Hono bootstrap to a NestJS app with a root module, config module, logger module, and health controller. Updated package dependencies, added Nest-based unit and integration tests, removed Hono references from service code and docs, and added architecture guidance that standardizes NestJS for backend services.
