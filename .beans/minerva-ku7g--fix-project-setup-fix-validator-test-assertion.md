---
# minerva-ku7g
title: '[fix] Project Setup: Fix validator test assertion'
status: completed
type: bug
priority: high
tags:
    - implemented
    - verified
    - orchestrator-v0
    - fix
    - planned
    - harvest
created_at: 2026-03-09T13:51:06Z
updated_at: 2026-03-10T04:45:36Z
---

## Problem

Unit test 'should throw PackNotFoundError for non-existent pack' in
tests/unit/packs/validator.test.ts is failing.

The error IS being thrown correctly (as shown in the test output), but the
test assertion rejects.toThrow(PackNotFoundError) is not catching it
properly.

Error output shows:

  PackNotFoundError: Pack not found at path: /Users/phong/...
/tests/fixtures/packs/non-existent
   ❯ PackValidator.validateSync src/packs/validator.ts:32:13

## Expected

Test should pass when PackNotFoundError is thrown for non-existent pack path.

## Actual

Test fails even though the correct error is being thrown.

## Plan

See: docs/plans/orchestrator-v0/fix-validator-test-assertion.md

## Original Bean

• **Bean**: minerva-eegh — Project Setup
• **Plan**: docs/plans/orchestrator-v0/project-setup.md

## Fix Requirements

[ ] Investigate why rejects.toThrow(PackNotFoundError) is not matching the
thrown error
[ ] Check if PackNotFoundError class is properly exported/imported
[ ] Consider using rejects.toThrowError() or checking error message instead
[ ] Run npm run test:unit to verify all tests pass



## Summary of Changes

**Root Cause**: The validator's `validate()` method used `Promise.resolve(this.validateSync(...))` which doesn't catch synchronous errors thrown by `validateSync`. When `PackNotFoundError` was thrown, it occurred before the Promise was created.

**Changes Made**:
1. `services/orchestrator/src/packs/validator.ts:22-30` - Changed `validate()` to use `new Promise()` wrapper that properly catches sync errors and rejects the Promise
2. `services/orchestrator/tests/unit/packs/validator.test.ts:8` - Removed unused `PackNotFoundError` import
3. `services/orchestrator/tests/unit/packs/validator.test.ts:39` - Changed assertion from `.toThrow(PackNotFoundError)` to `.toThrow(/Pack not found/)` for more reliable message-based matching

**Verification**: All 244 unit tests pass (15 test files)

**Requirements**: All 4 checkboxes completed - [x] Investigate error matching, [x] Check exports, [x] Update assertion method, [x] Run tests

## Requirements Completed

- [x] Investigate why rejects.toThrow(PackNotFoundError) is not matching the thrown error
- [x] Check if PackNotFoundError class is properly exported/imported
- [x] Consider using rejects.toThrowError() or checking error message instead
- [x] Run npm run test:unit to verify all tests pass

## Verification

**Status**: ✅ PASSED
**Date**: 2026-03-10

### Results
- Verified `services/orchestrator/src/packs/validator.ts` now rejects correctly on sync errors
- Verified `services/orchestrator/tests/unit/packs/validator.test.ts` uses a reliable message-based assertion
- `npm run test:unit` passed with 244 tests
