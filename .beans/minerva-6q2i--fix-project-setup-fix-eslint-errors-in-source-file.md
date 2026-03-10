---
# minerva-6q2i
title: '[fix] Project Setup: Fix ESLint errors in source files'
status: completed
type: bug
priority: high
tags:
    - orchestrator-v0
    - fix
    - implemented
    - planned
    - verified
    - harvest
created_at: 2026-03-09T13:50:41Z
updated_at: 2026-03-10T04:45:36Z
---

## Problem

 fails with 4 errors in source files:
- : 3 errors
  - Line 11: Async method 'shouldReuse' has no 'await' expression
  - Line 27: Async method 'shouldReuse' has no 'await' expression  
  - Line 58: Invalid type 'never' of template literal expression
- : 1 error
  - Line 77: Async method 'getWorkspace' has no 'await' expression

## Expected

 should pass with zero errors

## Actual

15 total lint errors (4 in source files, 11 in test files)

## Original Bean

- **Bean**: minerva-eegh — Project Setup
- **Plan**: docs/plans/orchestrator-v0/project-setup.md

## Fix Requirements
- [x] Fix async/await lint errors in `strategy.ts`
- [x] Fix async/await lint error in `workspace-manager.ts`
- [x] Consider adding eslint-disable comments where async interface requires async signature (not needed - used Promise.resolve/reject approach)
- [x] Run verification commands (lint, typecheck, test, build) to verify zero source errors



## Plan

Fix plan documented at: docs/plans/orchestrator-v0/fix-project-setup-fix-eslint-errors-in-source-file.md

### Summary
- 4 ESLint errors across 2 source files
- All errors are fixable by removing unnecessary async keywords and using Promise.resolve/reject
- 1 error requires type assertion for exhaustiveness checking
- No test changes needed - Promise return types preserved

## Summary of Changes

### Files Modified
1. **services/orchestrator/src/sandbox/strategy.ts**
   - Line 11: Changed `PerRunStrategy.shouldReuse()` from `async` to return `Promise.resolve(null)`
   - Line 27: Changed `PerUserStrategy.shouldReuse()` from `async` to return `Promise.resolve(workspace ?? null)`
   - Line 58: Added type assertion `${strategy as string}` for exhaustiveness check

2. **services/orchestrator/src/sandbox/workspace-manager.ts**
   - Line 77: Changed `getWorkspace()` from `async` to use `Promise.resolve()` and `Promise.reject()`

### Verification Results
- **Lint**: Zero errors in source files (4 fixed, 11 test file errors remain)
- **TypeCheck**: Passed with no errors
- **Tests**: All 267 tests passed (244 unit + 23 integration)
- **Build**: Successful compilation

### Implementation Notes
- Used `Promise.resolve()` and `Promise.reject()` instead of `async/await` for methods that don't perform async operations
- This satisfies the ESLint `@typescript-eslint/require-await` rule while maintaining the required Promise return types for interface compliance
- No `eslint-disable` comments needed - clean code approach used

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-10

### Results
- Verified lint fixes in `services/orchestrator/src/sandbox/strategy.ts` and `services/orchestrator/src/sandbox/workspace-manager.ts`
- `npm run typecheck`, `npm run test`, and `npm run build` passed
- `npm run lint` no longer reports the source-file errors this fix bean targeted
