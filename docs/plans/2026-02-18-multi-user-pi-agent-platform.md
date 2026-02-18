# Multi-User Pi Agent Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a scalable multi-user platform that runs pi coding agent sessions with lease-based single-writer workspaces, snapshot lifecycle (HOT/COLD), and multi-worker placement.

**Architecture:** Use a stateless control plane (API + lease + placement + metadata DB) and a stateful worker plane (supervisor + multiple agent runtimes per worker). Workspaces are local POSIX directories while HOT and serialized to object storage when COLD. Lease tokens fence writes and guarantee one active writer per workspace.

**Tech Stack:** TypeScript (Node.js 20), Fastify, PostgreSQL, Kysely, AWS SDK S3 client (MinIO-compatible), `tar` + `zstd` snapshot pipeline, Vitest, Docker Compose, `@mariozechner/pi-coding-agent`.

---

## Execution Notes

- Enforce skills during implementation: `@superpowers:test-driven-development`, `@superpowers:systematic-debugging`, `@superpowers:verification-before-completion`, `@superpowers:requesting-code-review`.
- Keep all implementation code under `src/`.
- Use one commit per task to preserve rollback points.
- Start with local MVP behavior before K8s/serverless deployment concerns.

### Task 1: Bootstrap Runtime, Tooling, and Module Layout

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vitest.config.ts`
- Create: `src/main.ts`
- Create: `src/config/env.ts`
- Test: `src/main.test.ts`

**Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { buildApp } from "./main";

describe("platform bootstrap", () => {
  it("creates a Fastify app", async () => {
    const app = await buildApp();
    expect(app).toBeDefined();
    await app.close();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/main.test.ts -v`
Expected: FAIL with module or export missing for `buildApp`.

**Step 3: Write minimal implementation**

```ts
import Fastify from "fastify";

export async function buildApp() {
  return Fastify({ logger: true });
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/main.test.ts -v`
Expected: PASS for `creates a Fastify app`.

**Step 5: Commit**

```bash
git add package.json tsconfig.json vitest.config.ts src/main.ts src/config/env.ts src/main.test.ts
git commit -m "chore: bootstrap typescript runtime and test harness"
```

### Task 2: Define Workspace and Lease Domain State Machine

**Files:**
- Create: `src/domain/workspace-state.ts`
- Create: `src/domain/lease.ts`
- Test: `src/domain/workspace-state.test.ts`
- Test: `src/domain/lease.test.ts`

**Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { assertValidTransition } from "./workspace-state";

describe("workspace transitions", () => {
  it("allows COLD -> RESTORING -> HOT -> SNAPSHOTTING -> COLD", () => {
    expect(() => assertValidTransition("COLD", "RESTORING")).not.toThrow();
    expect(() => assertValidTransition("RESTORING", "HOT")).not.toThrow();
    expect(() => assertValidTransition("HOT", "SNAPSHOTTING")).not.toThrow();
    expect(() => assertValidTransition("SNAPSHOTTING", "COLD")).not.toThrow();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/domain/workspace-state.test.ts -v`
Expected: FAIL with missing transition validator.

**Step 3: Write minimal implementation**

```ts
const allowed = new Map([
  ["COLD", new Set(["RESTORING"])],
  ["RESTORING", new Set(["HOT"])],
  ["HOT", new Set(["SNAPSHOTTING"])],
  ["SNAPSHOTTING", new Set(["COLD"])],
]);

export function assertValidTransition(from: string, to: string) {
  if (!allowed.get(from)?.has(to)) {
    throw new Error(`Invalid transition ${from} -> ${to}`);
  }
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/domain/workspace-state.test.ts src/domain/lease.test.ts -v`
Expected: PASS for transition and lease token invariants.

**Step 5: Commit**

```bash
git add src/domain/workspace-state.ts src/domain/lease.ts src/domain/workspace-state.test.ts src/domain/lease.test.ts
git commit -m "feat(domain): add workspace lifecycle and lease invariants"
```

### Task 3: Implement Metadata Persistence and Lease Repository

**Files:**
- Create: `src/db/client.ts`
- Create: `src/db/schema.ts`
- Create: `src/repositories/workspace-repository.ts`
- Create: `src/repositories/lease-repository.ts`
- Test: `src/repositories/lease-repository.test.ts`

**Step 1: Write the failing test**

```ts
it("enforces one active lease per workspace", async () => {
  const repo = buildLeaseRepositoryForTest();
  await repo.acquire({ workspaceId: "ws-1", workerId: "worker-a", ttlSeconds: 30 });
  await expect(
    repo.acquire({ workspaceId: "ws-1", workerId: "worker-b", ttlSeconds: 30 })
  ).rejects.toThrow(/active lease/i);
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/repositories/lease-repository.test.ts -v`
Expected: FAIL because repository is not implemented.

**Step 3: Write minimal implementation**

```ts
await db.transaction().execute(async (trx) => {
  const existing = await trx.selectFrom("leases").selectAll().where("workspace_id", "=", workspaceId).executeTakeFirst();
  if (existing && existing.expires_at > now()) throw new Error("active lease exists");
  await trx.insertInto("leases").values(row).onConflict((oc) => oc.column("workspace_id").doUpdateSet(row)).execute();
});
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/repositories/lease-repository.test.ts -v`
Expected: PASS for acquire, heartbeat/renew, expiry, and steal-after-expiry behavior.

**Step 5: Commit**

```bash
git add src/db/client.ts src/db/schema.ts src/repositories/workspace-repository.ts src/repositories/lease-repository.ts src/repositories/lease-repository.test.ts
git commit -m "feat(control-plane): persist workspace metadata and lease records"
```

### Task 4: Build Lease Manager with Fencing Tokens

**Files:**
- Create: `src/control-plane/lease-manager.ts`
- Create: `src/control-plane/errors.ts`
- Test: `src/control-plane/lease-manager.test.ts`

**Step 1: Write the failing test**

```ts
it("rejects heartbeat with stale lease token", async () => {
  const manager = buildLeaseManagerForTest();
  const lease = await manager.acquire("ws-1", "worker-a");
  await manager.forceExpire("ws-1");
  const newLease = await manager.acquire("ws-1", "worker-b");
  await expect(manager.heartbeat("ws-1", lease.leaseToken)).rejects.toThrow(/fenced/i);
  expect(newLease.leaseToken).not.toBe(lease.leaseToken);
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/control-plane/lease-manager.test.ts -v`
Expected: FAIL with missing fence enforcement.

**Step 3: Write minimal implementation**

```ts
if (record.lease_token !== leaseToken) {
  throw new LeaseFencedError(workspaceId, leaseToken);
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/control-plane/lease-manager.test.ts -v`
Expected: PASS for acquire, renew, release, and token fencing scenarios.

**Step 5: Commit**

```bash
git add src/control-plane/lease-manager.ts src/control-plane/errors.ts src/control-plane/lease-manager.test.ts
git commit -m "feat(control-plane): add lease manager with fencing guarantees"
```

### Task 5: Implement Snapshot Store (tar.zst + Manifest)

**Files:**
- Create: `src/storage/snapshot-store.ts`
- Create: `src/storage/object-store.ts`
- Create: `src/storage/manifest.ts`
- Test: `src/storage/snapshot-store.test.ts`

**Step 1: Write the failing test**

```ts
it("round-trips workspace snapshot via tar.zst archive", async () => {
  const store = buildSnapshotStoreForTest();
  const version = await store.snapshot("ws-1", "/tmp/ws-1");
  await fs.rm("/tmp/ws-1", { recursive: true, force: true });
  await store.restore("ws-1", version, "/tmp/ws-1");
  expect(await fs.readFile("/tmp/ws-1/README.md", "utf8")).toContain("workspace");
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/storage/snapshot-store.test.ts -v`
Expected: FAIL with missing snapshot/restore implementation.

**Step 3: Write minimal implementation**

```ts
await execa("tar", ["-C", workspacePath, "-cf", "-", "."]).pipe(execa("zstd", ["-q", "-o", archivePath]).stdin!);
await objectStore.putObject(snapshotKey, createReadStream(archivePath), metadata);
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/storage/snapshot-store.test.ts -v`
Expected: PASS for archive upload, manifest integrity, restore extraction.

**Step 5: Commit**

```bash
git add src/storage/snapshot-store.ts src/storage/object-store.ts src/storage/manifest.ts src/storage/snapshot-store.test.ts
git commit -m "feat(storage): add tar.zst snapshot and restore pipeline"
```

### Task 6: Add Workspace Local Filesystem Manager

**Files:**
- Create: `src/worker/workspace-manager.ts`
- Create: `src/worker/path-sharding.ts`
- Test: `src/worker/workspace-manager.test.ts`

**Step 1: Write the failing test**

```ts
it("creates sharded workspace path under local root", async () => {
  const manager = buildWorkspaceManager("/mnt/workspaces");
  const path = await manager.ensureWorkspacePath("ab12cd34");
  expect(path).toBe("/mnt/workspaces/ab/ab12cd34");
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/worker/workspace-manager.test.ts -v`
Expected: FAIL because sharding and safety checks are absent.

**Step 3: Write minimal implementation**

```ts
export function shardPrefix(workspaceId: string): string {
  return workspaceId.slice(0, 2);
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/worker/workspace-manager.test.ts -v`
Expected: PASS for sharding, directory creation, and path traversal rejection.

**Step 5: Commit**

```bash
git add src/worker/workspace-manager.ts src/worker/path-sharding.ts src/worker/workspace-manager.test.ts
git commit -m "feat(worker): add local workspace path and filesystem guards"
```

### Task 7: Wrap pi SDK in AgentHandle and Supervisor Runtime

**Files:**
- Create: `src/worker/agent-handle.ts`
- Create: `src/worker/supervisor.ts`
- Create: `src/worker/agent-registry.ts`
- Test: `src/worker/agent-handle.test.ts`
- Test: `src/worker/supervisor.test.ts`

**Step 1: Write the failing test**

```ts
it("binds agent tools to workspace cwd", async () => {
  const handle = await createAgentHandle({
    workspacePath: "/mnt/workspaces/ab/ws-1",
    workspaceId: "ws-1",
  });
  expect(handle.cwd).toBe("/mnt/workspaces/ab/ws-1");
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/worker/agent-handle.test.ts src/worker/supervisor.test.ts -v`
Expected: FAIL with missing agent wrapper.

**Step 3: Write minimal implementation**

```ts
const tools = createCodingTools(workspacePath);
const { session } = await createAgentSession({ tools });
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/worker/agent-handle.test.ts src/worker/supervisor.test.ts -v`
Expected: PASS for agent spawn, prompt streaming proxy, and clean shutdown.

**Step 5: Commit**

```bash
git add src/worker/agent-handle.ts src/worker/supervisor.ts src/worker/agent-registry.ts src/worker/agent-handle.test.ts src/worker/supervisor.test.ts
git commit -m "feat(worker): add pi sdk agent handle and multi-agent supervisor"
```

### Task 8: Implement Worker Service API for Prompt + Lease Heartbeat

**Files:**
- Create: `src/worker/worker-server.ts`
- Create: `src/worker/routes/prompt.ts`
- Create: `src/worker/routes/heartbeat.ts`
- Test: `src/worker/worker-server.test.ts`

**Step 1: Write the failing test**

```ts
it("rejects prompt when lease token is stale", async () => {
  const app = await buildWorkerServerForTest();
  const response = await app.inject({
    method: "POST",
    url: "/workspaces/ws-1/prompt",
    headers: { "x-lease-token": "stale-token" },
    payload: { prompt: "hello" },
  });
  expect(response.statusCode).toBe(409);
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/worker/worker-server.test.ts -v`
Expected: FAIL due to missing route/fencing integration.

**Step 3: Write minimal implementation**

```ts
if (!leaseManager.isTokenCurrent(workspaceId, req.headers["x-lease-token"])) {
  return reply.status(409).send({ code: "LEASE_FENCED" });
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/worker/worker-server.test.ts -v`
Expected: PASS for fencing, prompt streaming, and heartbeat renewals.

**Step 5: Commit**

```bash
git add src/worker/worker-server.ts src/worker/routes/prompt.ts src/worker/routes/heartbeat.ts src/worker/worker-server.test.ts
git commit -m "feat(worker): expose fenced prompt and heartbeat endpoints"
```

### Task 9: Implement Control Plane Router and Placement Policy

**Files:**
- Create: `src/control-plane/router-server.ts`
- Create: `src/control-plane/routes/acquire-lease.ts`
- Create: `src/control-plane/routes/release-lease.ts`
- Create: `src/control-plane/placement.ts`
- Test: `src/control-plane/router-server.test.ts`

**Step 1: Write the failing test**

```ts
it("places workspace on least-loaded worker and returns lease token", async () => {
  const app = await buildRouterForTest({
    workers: [{ id: "w1", activeAgents: 9 }, { id: "w2", activeAgents: 2 }],
  });
  const response = await app.inject({ method: "POST", url: "/v1/workspaces/ws-1/lease" });
  expect(response.statusCode).toBe(200);
  expect(response.json().workerId).toBe("w2");
  expect(response.json().leaseToken).toMatch(/^lease_/);
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/control-plane/router-server.test.ts -v`
Expected: FAIL because router/placement is not implemented.

**Step 3: Write minimal implementation**

```ts
export function pickWorker(workers: WorkerLoad[]): WorkerLoad {
  return [...workers].sort((a, b) => a.activeAgents - b.activeAgents)[0];
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/control-plane/router-server.test.ts -v`
Expected: PASS for placement, lease acquisition, and worker routing response.

**Step 5: Commit**

```bash
git add src/control-plane/router-server.ts src/control-plane/routes/acquire-lease.ts src/control-plane/routes/release-lease.ts src/control-plane/placement.ts src/control-plane/router-server.test.ts
git commit -m "feat(control-plane): add placement-aware lease routing api"
```

### Task 10: Add HOT/COLD Lifecycle Orchestration and Idle Eviction

**Files:**
- Create: `src/control-plane/lifecycle-orchestrator.ts`
- Create: `src/worker/eviction-loop.ts`
- Test: `src/control-plane/lifecycle-orchestrator.test.ts`
- Test: `src/worker/eviction-loop.test.ts`

**Step 1: Write the failing test**

```ts
it("evicts idle HOT workspace to COLD snapshot", async () => {
  const orchestrator = buildLifecycleOrchestratorForTest({ idleTtlMs: 1000 });
  await orchestrator.markPromptActivity("ws-1");
  await advanceTimeBy(1100);
  await orchestrator.runEvictionSweep();
  expect(await orchestrator.workspaceState("ws-1")).toBe("COLD");
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/control-plane/lifecycle-orchestrator.test.ts src/worker/eviction-loop.test.ts -v`
Expected: FAIL since idle eviction pipeline is absent.

**Step 3: Write minimal implementation**

```ts
if (workspace.state === "HOT" && now - workspace.lastActivityAt > idleTtlMs) {
  await supervisor.stopAgent(workspace.id);
  await snapshotStore.snapshot(workspace.id, workspace.path);
  await workspaceRepo.markCold(workspace.id);
  await workspaceManager.remove(workspace.id);
}
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/control-plane/lifecycle-orchestrator.test.ts src/worker/eviction-loop.test.ts -v`
Expected: PASS for idle eviction and state transitions HOT -> SNAPSHOTTING -> COLD.

**Step 5: Commit**

```bash
git add src/control-plane/lifecycle-orchestrator.ts src/worker/eviction-loop.ts src/control-plane/lifecycle-orchestrator.test.ts src/worker/eviction-loop.test.ts
git commit -m "feat(lifecycle): add idle eviction and snapshot transition orchestration"
```

### Task 11: Add Crash Recovery and Lease Reacquisition Flow

**Files:**
- Create: `src/control-plane/recovery-service.ts`
- Create: `src/worker/startup-reconciler.ts`
- Test: `src/control-plane/recovery-service.test.ts`
- Test: `src/worker/startup-reconciler.test.ts`

**Step 1: Write the failing test**

```ts
it("reassigns expired workspace lease to a new worker after crash", async () => {
  const recovery = buildRecoveryServiceForTest();
  await recovery.seedLease({ workspaceId: "ws-1", workerId: "dead-worker", expired: true });
  const reassigned = await recovery.reassignExpiredLease("ws-1", "new-worker");
  expect(reassigned.workerId).toBe("new-worker");
  expect(reassigned.state).toBe("RESTORING");
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/control-plane/recovery-service.test.ts src/worker/startup-reconciler.test.ts -v`
Expected: FAIL with recovery/reconcile logic missing.

**Step 3: Write minimal implementation**

```ts
await leaseManager.acquireStealExpired(workspaceId, newWorkerId);
await workspaceRepo.transition(workspaceId, "COLD", "RESTORING");
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/control-plane/recovery-service.test.ts src/worker/startup-reconciler.test.ts -v`
Expected: PASS for expired-lease steal and startup cleanup of orphaned processes.

**Step 5: Commit**

```bash
git add src/control-plane/recovery-service.ts src/worker/startup-reconciler.ts src/control-plane/recovery-service.test.ts src/worker/startup-reconciler.test.ts
git commit -m "feat(recovery): add crash recovery and lease reassignment flow"
```

### Task 12: End-to-End Local Stack and Verification Suite

**Files:**
- Create: `src/e2e/multi-user-flow.e2e.test.ts`
- Create: `src/e2e/crash-recovery.e2e.test.ts`
- Create: `src/dev/docker-compose.yml`
- Create: `src/dev/minio-init.sh`
- Create: `README.md`

**Step 1: Write the failing test**

```ts
it("handles two users concurrently without workspace state bleed", async () => {
  const system = await bootTestStack();
  const [u1, u2] = await Promise.all([
    system.prompt("workspace-a", "create file a.txt"),
    system.prompt("workspace-b", "create file b.txt"),
  ]);
  expect(u1.workspaceId).toBe("workspace-a");
  expect(u2.workspaceId).toBe("workspace-b");
  expect(await system.fileExists("workspace-a", "b.txt")).toBe(false);
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test -- src/e2e/multi-user-flow.e2e.test.ts src/e2e/crash-recovery.e2e.test.ts -v`
Expected: FAIL before local stack wiring is complete.

**Step 3: Write minimal implementation**

```yaml
services:
  postgres:
    image: postgres:16
  minio:
    image: minio/minio
  control-plane:
    build: .
  worker:
    build: .
```

**Step 4: Run test to verify it passes**

Run: `npm run test -- src/e2e/multi-user-flow.e2e.test.ts src/e2e/crash-recovery.e2e.test.ts -v`
Expected: PASS for concurrency, snapshot restore, lease fencing, and crash reassignment.

**Step 5: Commit**

```bash
git add src/e2e/multi-user-flow.e2e.test.ts src/e2e/crash-recovery.e2e.test.ts src/dev/docker-compose.yml src/dev/minio-init.sh README.md
git commit -m "test(e2e): validate multi-user isolation, lifecycle, and recovery"
```

## Final Verification Checklist

1. Run: `npm run test`
Expected: all unit/integration/e2e tests PASS.

2. Run: `npm run lint`
Expected: no lint errors.

3. Run: `npm run typecheck`
Expected: no TypeScript errors.

4. Run: `docker compose -f src/dev/docker-compose.yml up -d && npm run test -- src/e2e -v`
Expected: local stack healthy and e2e tests PASS.

5. Run: `git status --short`
Expected: clean working tree after the last commit.

