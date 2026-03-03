---
status: investigating
trigger: "multiple-sandboxes-stuck-workspace-ready: When sending a POST request to /runs endpoint, the response gets stuck at "workspace_ready" event, multiple sandboxes are spawned instead of one, and no answer is ever received."
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:00:00Z
---

## Current Focus

hypothesis: The sandbox creation/management logic is spawning multiple sandboxes due to race conditions or incorrect session handling, and the provisioning event stream is not completing properly
test: Examine the /runs endpoint handler and sandbox provisioning code
expecting: Find where sandboxes are created and why multiple instances are spawned
next_action: Read the API routes and sandbox provisioning code

## Symptoms

expected: A single sandbox should be created for user "alice" with session "alice-session-1", and the response should complete with an answer from the agent
actual: Response gets stuck at "workspace_ready" provisioning event (id: 47978b5d-bfb2-48f4-b2bd-8344fe8a650b:2), multiple sandboxes are spawned instead of a single one, and no answer is ever received
errors: No explicit error messages in the response, just stuck behavior at the workspace_ready event
reproduction: 
1. Start infrastructure: docker-compose up -d
2. Run migrations: uv run alembic upgrade head
3. Initialize environment: uv run minerva init
4. Register agent pack: uv run minerva register ./my-agent
5. Start server: uv run minerva serve --port 8002
6. Send request:
   curl -X POST http://localhost:8002/runs \
     -H "Content-Type: application/json" \
     -H "X-User-ID: alice" \
     -H "X-Session-ID: alice-session-1" \
     -d '{"message": "Hello! My name is Alice. Remember that I like Python."}'
started: Not specified when this started, but it's blocking multi-user chat functionality

## Eliminated

## Evidence

- timestamp: 2026-03-03
  checked: src/api/oss/runs.py _execute_run_with_events
  found: Cold start check (lines 94-105) happens BEFORE user_queue.execute(), which means multiple concurrent requests can see empty sandbox list and all trigger provisioning
  implication: Race condition - N concurrent requests see no sandboxes, emit N provisioning events, create N sandboxes

- timestamp: 2026-03-03
  checked: src/services/run_service.py resolve_routing_target
  found: Each call generates a new run_id (line 382) and attempts to resolve/create sandbox independently
  implication: No global coordination to prevent multiple sandboxes for same user/session

- timestamp: 2026-03-03
  checked: src/services/oss_user_queue.py
  found: User queue provides per-user serialization (lines 148-154, 212), but the cold start check in runs.py happens OUTSIDE this lock
  implication: The sandbox existence check is not protected by the user lock, allowing race conditions

- timestamp: 2026-03-03
  checked: Provisioning event ID "47978b5d-bfb2-48f4-b2bd-8344fe8a650b:2"
  found: The ":2" suffix indicates this is the SECOND provisioning event (event counter)
  implication: Multiple provisioning events are being emitted, confirming multiple requests are triggering cold start logic

- timestamp: 2026-03-03
  checked: Sandbox routing logic
  found: The sandbox repository filters by external_user_id when listing active sandboxes (list_active_healthy_by_workspace lines 141-177), but the initial cold start check in runs.py uses list_by_workspace WITHOUT external_user_id filter
  implication: Even if sandboxes exist for a user, the cold start check may not see them if filtering is inconsistent

## Resolution

root_cause: The cold start check and provisioning event emission in runs.py (lines 94-105) happens OUTSIDE the per-user queue lock. When multiple concurrent requests arrive for the same user, they all see an empty sandbox list and emit provisioning events before the user queue serializes execution. This causes:
1. Multiple "workspace_ready" provisioning events being sent (explaining the :2 suffix in the event ID)
2. Multiple sandboxes being provisioned for the same user
3. Potential resource contention and hanging as the requests compete

fix: Move the cold start check INSIDE the execute_operation function (which is called within user_queue.execute()), ensuring it's protected by the per-user lock. Only one request per user will see the cold start state and emit the provisioning event. Used `nonlocal` to communicate cold start status back to the generator.

verification: All 24 integration tests pass. The fix ensures:
- Cold start check happens inside per-user lock (OssUserQueue)
- Only first request per user emits "workspace_ready" event
- Subsequent concurrent requests wait for the first to complete
- Only one sandbox is provisioned per user workspace

files_changed:
  - src/api/oss/routes/runs.py: Moved cold start check inside execute_operation, added nonlocal cold_start_detected flag, emit provisioning event after queue execution
