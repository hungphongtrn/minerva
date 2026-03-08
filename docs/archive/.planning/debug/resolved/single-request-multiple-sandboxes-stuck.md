---
status: resolved
trigger: "single-request-multiple-sandboxes-stuck"
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:15:00Z
---

## Current Focus

hypothesis: Multiple sandboxes are spawned because _provision_with_bounded_retry creates a new sandbox DB record on each retry attempt before provider.provision_sandbox() succeeds

test: Examine the _provision_sandbox method to see if it creates DB records before provider provisioning succeeds

expecting: Find that _repository.create() is called before provider.provision_sandbox(), and on retry, a new record is created even if previous ones exist

next_action: Read _provision_sandbox code path carefully and check SandboxInstanceRepository.create()

## Symptoms

expected: A single sandbox should be created for user "alice" with session "alice-session-1", and the response should complete with an answer from the agent
actual: Response gets stuck at "workspace_ready" provisioning event (id: 47978b5d-bfb2-48f4-b2bd-8344fe8a650b:2), multiple sandboxes are spawned from a SINGLE request, and no answer is ever received
errors: No explicit error messages, just stuck behavior at the workspace_ready event with event ID showing `:2` suffix
reproduction:
1. Start infrastructure: docker-compose up -d
2. Run migrations: uv run alembic upgrade head
3. Initialize environment: uv run minerva init
4. Register agent pack: uv run minerva register ./my-agent
5. Start server: uv run minerva serve --port 8002
6. Send SINGLE request:
   curl -X POST http://localhost:8002/runs \
     -H "Content-Type: application/json" \
     -H "X-User-ID: alice" \
     -H "X-Session-ID: alice-session-1" \
     -d '{"message": "Hello! My name is Alice. Remember that I like Python."}'
timeline: Current issue blocking multi-user chat functionality
additional_context: Previous fix (commit 2ec69b9) addressed race condition for concurrent requests, but this is a SINGLE request spawning multiple sandboxes

## Eliminated

## Evidence

- timestamp: 2026-03-03T18:05:00Z
  checked: _provision_sandbox method in sandbox_orchestrator_service.py (lines 606-810)
  found: |
    1. Creates DB record FIRST: self._repository.create() at line 720
    2. Updates state to CREATING at line 729
    3. THEN calls provider: self._provider.provision_sandbox(config) at line 743
    4. On failure, returns error result but orphaned DB record remains
  implication: Each retry creates a new orphan DB record

- timestamp: 2026-03-03T18:06:00Z
  checked: _provision_with_bounded_retry method (lines 462-559)
  found: |
    Retry loop at lines 497-541 calls _provision_sandbox() on each retry
    No cleanup of previous failed sandbox records before retry
    MAX_REPROVISION_ATTEMPTS = 3, so up to 3 orphaned records can be created
  implication: Single request can spawn multiple sandboxes due to retry logic

- timestamp: 2026-03-03T18:07:00Z
  checked: execute_operation in oss/routes/runs.py (lines 99-122)
  found: |
    Cold start check (lines 104-110) happens INSIDE execute_operation
    But execute_operation is called WITHIN the user_queue lock
    However, the sandbox list check is done BEFORE provisioning starts
    The provisioning happens in run_service.execute_with_routing -> resolve_routing_target
  implication: Cold start check IS protected by user queue lock, but provisioning retries bypass this

## Resolution

root_cause: |
  In sandbox_orchestrator_service.py, _provision_sandbox() creates a database record 
  BEFORE calling provider.provision_sandbox(). When provisioning fails and the retry 
  loop in _provision_with_bounded_retry() kicks in, it calls _provision_sandbox() 
  again, creating ANOTHER database record. This results in multiple sandbox records 
  for a single request. The orphaned records remain in PENDING/CREATING states.
  
  File: src/services/sandbox_orchestrator_service.py
  Lines: 720 (create), 729 (state=CREATING), 743 (provider provision)
  
  The fix is to check for existing PENDING/CREATING sandboxes before creating new ones,
  OR to pass the existing sandbox record to retry attempts instead of creating new ones.

fix: |
  Added _find_in_progress_sandbox() method to look for existing PENDING/CREATING 
  sandboxes matching the workspace/profile/pack criteria. Modified _provision_sandbox()
  to check for existing sandbox before creating new one. On retry attempts, the 
  existing sandbox record is reused instead of creating a duplicate.
  
  Changes made:
  1. Added `from sqlalchemy import select, and_` import at top of file
  2. Added _find_in_progress_sandbox() method (lines 463-505)
  3. Modified _provision_sandbox() to check for existing sandbox before creating (lines 765-790)

verification: |
  1. Send single POST /runs request
  2. Verify only ONE sandbox record is created in DB even if provisioning retries
  3. Verify request completes successfully (or fails gracefully without orphaned records)

files_changed:
  - src/services/sandbox_orchestrator_service.py
