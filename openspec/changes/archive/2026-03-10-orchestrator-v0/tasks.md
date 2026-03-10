## 1. Project Setup

- [x] 1.1 Decide repository layout for the TypeScript orchestrator (single service vs apps/ directory) and document it
- [x] 1.2 Add Node.js/TypeScript project scaffolding (package manager, tsconfig, lint/format)
- [x] 1.3 Add dependencies: `@mariozechner/pi-agent-core`, `@mariozechner/pi-ai`, Daytona TS SDK, and an HTTP server framework

## 2. Run Model + Scheduling

- [x] 2.1 Define run IDs, run states (queued/running/completed/failed/cancelled), and minimal run metadata model
- [x] 2.2 Implement per-user queue/lease to ensure one active run per `user_id`
- [x] 2.3 Implement cancellation and timeouts at the orchestrator level (AbortSignal propagation)

## 3. SSE API

- [x] 3.1 Define the v0 SSE event envelope (`type`, `run_id`, `ts`, `seq`, payload)
- [x] 3.2 Implement SSE endpoint for a run with ordered event delivery and connection cleanup
- [x] 3.3 Map pi-agent-core message streaming events to SSE (text deltas, message lifecycle)

## 4. Agent Pack Loading

- [x] 4.1 Implement agent pack validation (must include `AGENTS.md`)
- [x] 4.2 Load `.agents/skills/**/SKILL.md` as plain text context (instructional-only)
- [x] 4.3 Build the final system prompt/context assembly rules for v0

## 5. Daytona Sandbox Adapter

- [x] 5.1 Implement sandbox provisioning/reuse strategy (workspace per run or per user, v0 default)
- [x] 5.2 Implement `bash` execution with stdout/stderr streaming and exit status capture
- [x] 5.3 Implement `read` and `write` operations with workspace-root scoping and path traversal protection
- [x] 5.4 Validate/verify that sandboxes have no general outbound network in the chosen Daytona configuration

## 6. Tool Integration (pi-agent-core)

- [x] 6.1 Define pi-agent-core tools for `bash`, `read`, and `write` with JSON-schema parameters
- [x] 6.2 Wire tool execution lifecycle events (`tool_execution_*`) into SSE
- [x] 6.3 Ensure tool errors surface deterministically as tool error results

## 7. Testing + Docs

- [x] 7.1 Add unit tests for queue/lease behavior (single active run per user)
- [x] 7.2 Add unit tests for SSE sequencing (`seq` monotonicity) and termination at run completion
- [x] 7.3 Add integration test (or harness) that runs a simple `bash` command in Daytona and streams output
- [x] 7.4 Update docs to reflect implemented API endpoints and event schema
