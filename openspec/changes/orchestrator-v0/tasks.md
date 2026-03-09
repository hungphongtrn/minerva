## 1. Project Setup

- [ ] 1.1 Decide repository layout for the TypeScript orchestrator (single service vs apps/ directory) and document it
- [ ] 1.2 Add Node.js/TypeScript project scaffolding (package manager, tsconfig, lint/format)
- [ ] 1.3 Add dependencies: `@mariozechner/pi-agent-core`, `@mariozechner/pi-ai`, Daytona TS SDK, and an HTTP server framework

## 2. Run Model + Scheduling

- [ ] 2.1 Define run IDs, run states (queued/running/completed/failed/cancelled), and minimal run metadata model
- [ ] 2.2 Implement per-user queue/lease to ensure one active run per `user_id`
- [ ] 2.3 Implement cancellation and timeouts at the orchestrator level (AbortSignal propagation)

## 3. SSE API

- [ ] 3.1 Define the v0 SSE event envelope (`type`, `run_id`, `ts`, `seq`, payload)
- [ ] 3.2 Implement SSE endpoint for a run with ordered event delivery and connection cleanup
- [ ] 3.3 Map pi-agent-core message streaming events to SSE (text deltas, message lifecycle)

## 4. Agent Pack Loading

- [ ] 4.1 Implement agent pack validation (must include `AGENTS.md`)
- [ ] 4.2 Load `.agents/skills/**/SKILL.md` as plain text context (instructional-only)
- [ ] 4.3 Build the final system prompt/context assembly rules for v0

## 5. Daytona Sandbox Adapter

- [ ] 5.1 Implement sandbox provisioning/reuse strategy (workspace per run or per user, v0 default)
- [ ] 5.2 Implement `bash` execution with stdout/stderr streaming and exit status capture
- [ ] 5.3 Implement `read` and `write` operations with workspace-root scoping and path traversal protection
- [ ] 5.4 Validate/verify that sandboxes have no general outbound network in the chosen Daytona configuration

## 6. Tool Integration (pi-agent-core)

- [ ] 6.1 Define pi-agent-core tools for `bash`, `read`, and `write` with JSON-schema parameters
- [ ] 6.2 Wire tool execution lifecycle events (`tool_execution_*`) into SSE
- [ ] 6.3 Ensure tool errors surface deterministically as tool error results

## 7. Testing + Docs

- [ ] 7.1 Add unit tests for queue/lease behavior (single active run per user)
- [ ] 7.2 Add unit tests for SSE sequencing (`seq` monotonicity) and termination at run completion
- [ ] 7.3 Add integration test (or harness) that runs a simple `bash` command in Daytona and streams output
- [ ] 7.4 Update docs to reflect implemented API endpoints and event schema
