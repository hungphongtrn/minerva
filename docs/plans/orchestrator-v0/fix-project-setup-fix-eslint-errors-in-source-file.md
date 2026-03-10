# Fix Plan: ESLint Errors in Source Files

**Bean**: minerva-6q2i  
**Scope**: Fix ESLint errors blocking project setup verification  
**Priority**: High

---

## 1. Root Cause Analysis

The ESLint errors are caused by:

### 1.1 Async Methods Without Await (`@typescript-eslint/require-await`)

Three methods are marked `async` but contain no `await` expressions:

- **`PerRunStrategy.shouldReuse()`** (strategy.ts:11) - Returns `null` immediately
- **`PerUserStrategy.shouldReuse()`** (strategy.ts:27) - Accesses in-memory Map synchronously  
- **`WorkspaceManager.getWorkspace()`** (workspace-manager.ts:77) - Accesses in-memory Map synchronously

**Root Cause**: These methods implement interfaces that require `Promise<...>` return types, but the implementations are synchronous. The `async` keyword was added to satisfy the interface contract, but the implementations don't need actual async operations.

### 1.2 Invalid `never` Type in Template Literal (`@typescript-eslint/restrict-template-expressions`)

- **`createProvisioningStrategy()`** (strategy.ts:58) - The `strategy` variable has type `never` at this point (exhaustiveness check in switch statement), but ESLint rejects using `never` in template literals.

**Root Cause**: TypeScript's exhaustiveness checking causes the `default` case to have `never` type, which ESLint's `restrict-template-expressions` rule flags as invalid.

---

## 2. Specific File Changes

### File: `/services/orchestrator/src/sandbox/strategy.ts`

#### Change 2.1: Remove async from `PerRunStrategy.shouldReuse()`

**Line 11**: Change from:
```typescript
async shouldReuse(_userId: string): Promise<null> {
  return null;
}
```

To:
```typescript
shouldReuse(_userId: string): Promise<null> {
  return Promise.resolve(null);
}
```

**Rationale**: Interface requires `Promise<Workspace | null>` return type. Using `Promise.resolve()` satisfies the contract without marking the method `async`.

#### Change 2.2: Remove async from `PerUserStrategy.shouldReuse()`

**Line 27**: Change from:
```typescript
async shouldReuse(userId: string): Promise<Workspace | null> {
  const workspace = this.workspaces.get(userId);
  if (workspace) {
    return workspace;
  }
  return null;
}
```

To:
```typescript
shouldReuse(userId: string): Promise<Workspace | null> {
  const workspace = this.workspaces.get(userId);
  return Promise.resolve(workspace ?? null);
}
```

**Rationale**: Same approach - interface requires Promise return, implementation is synchronous.

#### Change 2.3: Fix `never` type in template literal

**Line 58**: Change from:
```typescript
throw new Error(`Unknown workspace strategy: ${strategy}`);
```

To:
```typescript
throw new Error(`Unknown workspace strategy: ${strategy as string}`);
```

**Rationale**: Type assertion to `string` satisfies ESLint while maintaining exhaustiveness checking. This is a standard pattern for unreachable code that should never execute.

### File: `/services/orchestrator/src/sandbox/workspace-manager.ts`

#### Change 2.4: Remove async from `getWorkspace()`

**Line 77**: Change from:
```typescript
async getWorkspace(workspaceId: string): Promise<Workspace> {
  const workspace = this.workspaces.get(workspaceId);
  if (!workspace) {
    throw new WorkspaceNotFoundError(workspaceId);
  }
  return workspace;
}
```

To:
```typescript
getWorkspace(workspaceId: string): Promise<Workspace> {
  const workspace = this.workspaces.get(workspaceId);
  if (!workspace) {
    return Promise.reject(new WorkspaceNotFoundError(workspaceId));
  }
  return Promise.resolve(workspace);
}
```

**Rationale**: Method only accesses in-memory Map synchronously. Using `Promise.resolve/reject` satisfies the Promise return type without async overhead. Note: This method may not implement an interface, but keeping Promise return maintains consistency with similar methods.

---

## 3. Test Updates

### No Test Changes Required

The existing tests in `strategy.test.ts` and `workspace-manager.ts` (integration tests) will continue to work because:

1. The return type remains `Promise<...>` in all cases
2. Tests already use `await` when calling these methods
3. The behavior is identical from the caller's perspective

### Regression Prevention

Add an ESLint check to CI to prevent similar issues:

```yaml
# .github/workflows/ci.yml (if exists) or similar
- name: Lint
  run: npm run lint
```

---

## 4. Verification Steps

### Step 4.1: Run ESLint

```bash
cd services/orchestrator
npm run lint
```

**Expected Result**: Zero errors in source files (`src/` directory)

### Step 4.2: Run Type Check

```bash
npm run typecheck
```

**Expected Result**: No type errors

### Step 4.3: Run Tests

```bash
npm run test
```

**Expected Result**: All tests pass

### Step 4.4: Verify Build

```bash
npm run build
```

**Expected Result**: Successful compilation

---

## 5. Reference Links

### Original Documentation
- [Project Setup Plan](./project-setup.md) - Original implementation plan
- [Bean: minerva-eegh](../../../.beans/minerva-eegh.md) - Original project setup bean

### Source Files (with errors)
- [`src/sandbox/strategy.ts`](../../../services/orchestrator/src/sandbox/strategy.ts) - Workspace provisioning strategies
- [`src/sandbox/workspace-manager.ts`](../../../services/orchestrator/src/sandbox/workspace-manager.ts) - Workspace lifecycle management

### TypeScript/ESLint Resources
- [TypeScript Handbook - Promise](https://www.typescriptlang.org/docs/handbook/basic-types.html#promise)
- [ESLint @typescript-eslint/require-await](https://typescript-eslint.io/rules/require-await/)
- [ESLint @typescript-eslint/restrict-template-expressions](https://typescript-eslint.io/rules/restrict-template-expressions/)

---

## 6. Summary

| File | Line | Error Type | Fix Strategy |
|------|------|------------|--------------|
| strategy.ts | 11 | Missing await | Remove async, use Promise.resolve |
| strategy.ts | 27 | Missing await | Remove async, use Promise.resolve |
| strategy.ts | 58 | Never type | Type assertion to string |
| workspace-manager.ts | 77 | Missing await | Remove async, use Promise.resolve/reject |

All fixes are minimal and targeted, maintaining the existing Promise-based API while satisfying ESLint rules.

---

*Fix Plan created: 2026-03-10*  
*Status: Ready for implementation*
