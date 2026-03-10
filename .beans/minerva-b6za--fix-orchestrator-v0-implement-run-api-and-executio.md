---
# minerva-b6za
title: '[fix] Orchestrator v0: implement run API and execution bridge'
status: completed
type: bug
priority: high
created_at: 2026-03-10T06:10:23Z
updated_at: 2026-03-10T06:41:46Z
parent: minerva-5rrj
---

Follow up on orchestrator-v0 verification gaps before archive.\n\nProblem:\n- The documented run API is missing from the NestJS service (POST /api/v0/runs, GET /api/v0/runs/:runId, POST /api/v0/runs/:runId/cancel).\n- The pi-agent-core execution bridge is not evident, so run execution and agent event forwarding are incomplete.\n\nExpected outcome:\n- The orchestrator exposes the documented run endpoints.\n- Starting a run executes the pi-agent-core loop and forwards lifecycle/message/tool events into SSE.\n- Docs match the shipped API and runtime behavior.\n\nVerification notes:\n- Keep the SSE-only implementation gap closed.\n- Add tests covering run creation/cancellation and end-to-end event flow.\n\n- [ ] Add NestJS controller/service wiring for create/get/cancel run endpoints\n- [ ] Implement the pi-agent-core run execution bridge\n- [ ] Forward agent lifecycle/message events into SSE during real runs\n- [ ] Add tests for run API and end-to-end execution flow\n- [x] Align API docs with the implemented behavior

## Summary of Changes

- Added a real run API surface for create, status, and cancel operations in the NestJS orchestrator.
- Implemented a pi-agent-core-backed execution bridge with sandbox tool wiring and SSE event forwarding.
- Added run API integration coverage, updated endpoint docs, and verified the service with tests, lint, and typecheck.
