# Session State

## Project Reference

See: .planning/PROJECT.md

## Position

**Milestone:** v1.0 milestone
**Current phase:** 03.4-picoclaw-bridge-gateway-audit-and-zeroclaw-migration
**Current plan:** 03
**Status:** In Progress

## Completed Plans

### Phase 03.4: Picoclaw Bridge Gateway Audit and ZeroClaw Migration

- [x] Plan 01: Picoclaw Gateway Audit Harness
  - Commits: 9a1334a, 9e1c453
  - Duration: 12 min
  - Artifacts: PicoclawGatewayAuditor class, audit CLI, 34 comprehensive tests

- [x] Plan 02: Daytona Picoclaw Audit Evidence Report
  - Commits: f0ec799, e311279
  - Duration: 3 min
  - Artifacts: Live Daytona audit integration test, audit report with verdict framework

- [x] Plan 03: Live Audit Execution and Migration Decision
  - Commits: 42b3e82
  - Duration: 8 min
  - Artifacts: Updated audit report with FAIL verdict, Zeroclaw spec.json, migration decision documented

### Phase 03.3: Close Pack-Mount Isolation and Identity-Collision Gaps

- [x] Plan 01: External Identity Infrastructure
  - Commits: 8323c0a, b3c0bf3
  - Duration: 5 min
  - Artifacts: ExternalIdentity model, settings, Alembic migration, rewritten identity resolution, preflight workspace validation

- [x] Plan 02: Mount Isolation and Per-User Routing
  - Commits: be91323, 30ec425
  - Duration: 3 min
  - Artifacts: Isolation constants, per-user sandbox keying, workspace symlinks

- [x] Plan 03: Wire Identity Forwarding and Local Compose Parity
  - Commits: e6d1a38, 6fe971a
  - Duration: 5 min
  - Artifacts: Bridge sender_id/session_id forwarding, RunService identity wiring, local_compose mount isolation parity

- [x] Plan 04: Wire Workspace-Config Preflight into Serve Startup
  - Commits: cc9526c, dab40a5
  - Duration: 2 min
  - Artifacts: Workspace preflight gate, regression tests, fail-closed behavior

- [x] Plan 05: Enforce Pack Mount Read-Only Contract
  - Commits: 13cece5, ac75e61
  - Duration: 4 min
  - Artifacts: Daytona read-only VolumeMount, provider parity tests, local_compose fail-fast guard

- [x] Plan 06: Plumb external_user_id end-to-end
  - Commits: 928805f, 78ec863
  - Duration: 6 min
  - Artifacts: Per-user sandbox routing keyed on (workspace_id, external_user_id), OSS ExternalPrincipal path, repository query filtering

### Phase 03.2: OSS Agent Server MVP

- [x] Plan 06: Close GAP-01 - Environment Contract Alignment
  - Commits: 0155071, cb738d6, c517c16
  - Duration: 2 min
  - Artifacts: Updated .env.example (140 lines), contract test

- [x] Plan 07: Close GAP-02 - Idempotent Snapshot Build
  - Commits: 9c2bf2a, 52bd9f6
  - Duration: 15 min
  - Artifacts: Idempotent DaytonaSnapshotBuildService with reused flag, 2 new tests

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Create a docker compose to spin up Postgres quickly | 2026-02-23 | 7c3080d | [001-create-a-docker-compose-to-spin-up-postg](./quick/001-create-a-docker-compose-to-spin-up-postg/) |
| 002 | Update docker-compose.yml to prepare minio dependencies | 2026-03-02 | e770c17 | [002-update-docker-compose-minio](./quick/002-update-docker-compose-minio/) |

## Decisions

1. **03.2-06**: Extracted template to `_render_env_example_template()` for reusability and testability
2. **03.2-06**: Contract test allows only trailing newline difference to ensure exact synchronization
3. **03.2-06**: ASCII-only .env.example for broad terminal/IDE compatibility
4. **03.2-07**: Use daytona.snapshot.get() before daytona.snapshot.create() for idempotent behavior
5. **03.2-07**: Add explicit `reused` boolean to SnapshotBuildResult for CLI/test observability
6. **03.2-07**: Fail closed on auth errors (don't attempt create if get fails with permission error)
7. **03.3-02**: Use module-level constants (PACK_MOUNT_PATH, WORKSPACE_PATH) to codify isolation contract
8. **03.3-02**: Symlink identity files using `ln -sf` for re-provisioning support
9. **03.3-02**: Hash external_user_id with SHA-256 for deterministic 10-char sandbox ref suffix
10. **03.3-02**: Identity verification checks workspace path to confirm symlinks work end-to-end
11. **03.3-01**: End-users NEVER create rows in the developer `users` table (security invariant)
12. **03.3-01**: All end-users resolve to the developer's workspace via MINERVA_WORKSPACE_ID
13. **03.3-01**: Workspace-scoped uniqueness via composite key (workspace_id, external_user_id)
14. **03.3-01**: Guest requests get no DB record and no session continuity
15. **03.3-03**: Forward raw external_user_id (from X-User-ID) as sender_id to Picoclaw - no hashing or transformation
16. **03.3-03**: Guest requests use generic 'guest' as sender_id - the agent knows it's a guest but has no unique identifier
17. **03.3-03**: Full mount isolation parity: local_compose uses same WORKSPACE_PATH as Daytona
18. **03.3-04**: Workspace check is Gate 2 (BLOCKING) after schema, before snapshot
19. **03.3-04**: Public check_workspace_configured() wrapper exposes private _check_workspace_configured()
20. **03.3-05**: Use VolumeMount.additional_properties for read_only flag (Daytona SDK pattern)
21. **03.3-05**: Provider parity through identical metadata keys (pack_mount_path, pack_mount_read_only)
22. **03.3-05**: Fail-closed guard in local_compose prevents dynamic paths under read-only pack mount
23. **03.3-06**: Repository filters by external_user_id only when explicitly provided (backwards compatible)
24. **03.3-06**: OSS principal detected by workspace_id + external_user_id attributes on principal
25. **03.3-06**: RunService uses _process_routing_target() helper for common routing result processing
26. **03.3-06**: Fixed list_identity_not_ready() SQLAlchemy query syntax (use .is_(False) not 'not' operator)
27. **03.4-01**: Audit harness supports both Daytona provisioning and direct gateway URL modes for flexibility
28. **03.4-01**: Four evidence categories (health, execute, streaming_probe, continuity_wiring) provide complete capability assessment
29. **03.4-01**: Mock-based tests patch at source module level (src.infrastructure.*) rather than in-script imports
30. **03.4-02**: Audit test asserts structural invariants, not PASS/FAIL - verdict is recorded in report
31. **03.4-02**: Integration tests that provision real infrastructure should skip when unconfigured
32. **03.4-02**: Soak criteria defined before migration decision: 24h minimum, >=100 runs, <1% error rate, zero auth failures
33. **03.4-03**: Picoclaw FAILED audit: /home/daytona/ permission error prevents sandbox provisioning
34. **03.4-03**: Decision: Proceed with Zeroclaw migration (Plans 04-05) - infrastructure incompatible
35. **03.4-03**: Audit-first decision: Run evidence collection before committing to migration path
36. **03.4-03**: Template-to-instance: spec.template.json -> spec.json with env-specific values

## Accumulated Context

### Roadmap Evolution

- Phase 03.4 inserted after Phase 3: Picoclaw bridge gateway audit and Zeroclaw migration (URGENT)
- Phase 03.3 inserted after Phase 3.2: Close pack-mount isolation and identity-collision gaps (URGENT)

### Pending Todos

- [x] Fix workspace/pack mount mixing static and dynamic data (infrastructure) - Completed in Plan 02
- [x] Resolve Identity Collision between Developer and End-User (auth) - Completed in Plan 01

## Session Log

- 2026-03-05: Completed plan 03.4-03 (Live Audit Execution and Migration Decision) - Live audit FAILED, Zeroclaw migration approved, spec.json created
- 2026-03-05: Completed plan 03.4-02 (Daytona Picoclaw Audit Evidence Report) - Live audit test with graceful skip, audit report with verdict framework
- 2026-03-05: Completed plan 03.4-01 (Picoclaw Gateway Audit Harness) - Audit runner with Daytona + direct modes, 34 tests
- 2026-03-02: Completed plan 03.3-06 (Plumb external_user_id end-to-end) - Phase 03.3 COMPLETE
- 2026-03-02: Completed plan 03.3-05 (Enforce Pack Mount Read-Only Contract)
- 2026-03-02: Completed plan 03.3-04 (Wire Workspace-Config Preflight into Serve Startup)
- 2026-03-02: Completed plan 03.3-01 (External Identity Infrastructure - Identity Collision Fix)
- 2026-03-02: Completed plan 03.3-02 (Mount Isolation and Per-User Routing)
- 2026-03-02: [Quick] Update docker-compose.yml to prepare minio dependencies
- 2026-03-02: Completed plan 03.2-07 (GAP-02 closure - Idempotent Snapshot Build)
- 2026-03-02: Completed plan 03.2-06 (GAP-01 closure)
- 2026-03-02: STATE.md regenerated by /gsd-health --repair

## Last Session

- **Stopped at:** Completed 03.4-03-Live-Audit-Execution-and-Migration-Decision
- **Resume file:** None
