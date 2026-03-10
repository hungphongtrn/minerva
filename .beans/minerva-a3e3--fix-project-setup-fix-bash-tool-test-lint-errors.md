---
# minerva-a3e3
title: '[fix] Project Setup: Fix bash tool test lint errors'
status: completed
type: bug
priority: high
tags:
    - harvest
    - orchestrator-v0
    - fix
    - implemented
    - verified
created_at: 2026-03-10T05:37:50Z
updated_at: 2026-03-10T05:43:58Z
---

## Problem

`services/orchestrator/src/tools/bash.test.ts` still fails lint with async generator errors, which keeps `minerva-eegh` from passing verification.

## Original Bean

- **Bean**: minerva-eegh — Project Setup
- **Traceability**: manual follow-up after second verification failure

## Fix Requirements
- [x] Remove async-generator lint violations from `services/orchestrator/src/tools/bash.test.ts`
- [x] Keep bash tool tests passing
- [x] Run lint for the affected file or project scope
- [x] Run relevant test coverage for bash tool behavior

## Summary of Changes

- Replaced async generator mocks in `services/orchestrator/src/tools/bash.test.ts` with small async-iterable helpers that return `Promise.resolve(...)` / `Promise.reject(...)`
- Preserved the same bash tool test scenarios while removing `require-await` lint violations
- Verified `npm run lint`, `npm run typecheck`, and `npm run test` in `services/orchestrator` all pass

## Verification

**Status**: PASSED
**Date**: 2026-03-10

### Results
- Removed async-generator lint violations from `services/orchestrator/src/tools/bash.test.ts`
- `npm run lint`, `npm run typecheck`, and `npm run test` all pass in `services/orchestrator`
- No escalation needed; this fix bean is verified
