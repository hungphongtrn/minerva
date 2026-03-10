---
# minerva-yaz0
title: Standardize orchestrator on NestJS
status: completed
type: task
created_at: 2026-03-09T09:26:19Z
updated_at: 2026-03-09T09:26:19Z
parent: minerva-5rrj
---

Standardize `services/orchestrator` on NestJS and update docs to reflect the architectural decision.

- [x] Find all stale backend framework references in the repo
- [x] Refactor services/orchestrator to use NestJS bootstrap, modules, controllers, and providers
- [x] Update tests and package configuration for NestJS
- [x] Update docs in docs/ and service docs to justify NestJS as the standard

## Summary of Changes

Standardized the orchestrator service on a NestJS app with a root module, config module, logger module, and health controller. Updated package dependencies, added Nest-based unit and integration tests, aligned service code and docs around NestJS, and added architecture guidance that standardizes NestJS for backend services.
