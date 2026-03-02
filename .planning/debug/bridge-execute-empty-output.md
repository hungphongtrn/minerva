---
status: investigating
trigger: "Investigate issue: bridge-execute-empty-output"
created: "2026-03-02"
updated: "2026-03-02"
---

## Current Focus

hypothesis: The bridge_execute step is completing instantly with empty data, suggesting either the bridge isn't properly configured or the sandbox spawning is failing silently.
test: Investigate the bridge_execute implementation and how it interacts with Daytona sandbox spawning
expecting: Find where the empty {} response is generated and why sandbox isn't spawning
next_action: Search codebase for bridge_execute implementation and understand the flow

## Symptoms

expected: Sandbox should be spawned and bridge should execute the run, returning the assistant's output.
actual: The run reaches `bridge_execute` step (after a ~10s delay in `queued`), and then immediately fires a `completed` event with empty data (`{}`). No output is returned, and user observes no sandbox spawning.
errors: No explicit error in the event stream, but the data is empty.
reproduction: 
curl -X POST http://localhost:8000/runs \
  -H "X-User-ID: test-user" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "hello",
    "agent_pack_id": "d99e6693-8d3a-4f9b-a016-5a05f3e8d763"
  }'
started: This happens after fixing the LifecycleTarget error.

## Eliminated

## Evidence

## Resolution

root_cause: 
fix: 
verification: 
files_changed: []
