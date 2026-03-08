---
status: verifying
trigger: "POST /runs endpoint fails with 'LifecycleTarget' object has no attribute 'agent_pack_id'"
created: 2026-03-02T00:00:00Z
updated: 2026-03-02T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - LifecycleTarget class is missing the agent_pack_id attribute
test: Add agent_pack_id field to LifecycleTarget dataclass
expecting: Code in run_service.py accessing routing.lifecycle_target.agent_pack_id will work
next_action: Add agent_pack_id field to LifecycleTarget and ensure it's populated in resolve_target()

## Symptoms

expected: The run should be executed successfully and return progress events without error.
actual: The run is queued but then fails immediately with a fatal error event.
errors: "'LifecycleTarget' object has no attribute 'agent_pack_id'"
reproduction: 
  curl -X POST http://localhost:8000/runs \
           -H "X-User-ID: test-user" \
           -H "X-Idempotency-Key: $(uuidgen)" \
           -H "Content-Type: application/json" \
           -d '{"message": "hello"}'
started: Just encountered this when calling the API endpoint.

## Eliminated

## Evidence

- timestamp: 2026-03-02
  checked: LifecycleTarget class definition in workspace_lifecycle_service.py lines 31-47
  found: The dataclass has workspace, lease_acquired, lease_result, sandbox, routing_result, error, restore_state, restore_checkpoint_id, queued fields
  implication: agent_pack_id is NOT in the dataclass definition

- timestamp: 2026-03-02
  checked: run_service.py _execute_via_bridge method at lines 861 and 909
  found: Code accesses routing.lifecycle_target.agent_pack_id
  implication: This is where the AttributeError originates

- timestamp: 2026-03-02
  checked: resolve_target method in workspace_lifecycle_service.py
  found: agent_pack_id is accepted as parameter and passed to _resolve_sandbox, but never stored in LifecycleTarget
  implication: The field needs to be added and populated

- timestamp: 2026-03-02
  checked: Syntax validation of modified files
  found: Both workspace_lifecycle_service.py and run_service.py compile without errors
  implication: Fix is syntactically correct

## Resolution

root_cause: The LifecycleTarget dataclass was missing the agent_pack_id field. The run_service.py code at lines 861 and 909 attempts to access routing.lifecycle_target.agent_pack_id, but this attribute doesn't exist in the dataclass.

fix: Added agent_pack_id: Optional[str] = None field to LifecycleTarget dataclass and populated it in all 4 places where LifecycleTarget is instantiated in resolve_target() method.

verification: Syntax check passed for both files. The POST /runs endpoint should now work without the AttributeError.
files_changed:
  - src/services/workspace_lifecycle_service.py:
    - Added agent_pack_id field to LifecycleTarget dataclass
    - Populated agent_pack_id in all 4 LifecycleTarget instantiations in resolve_target()
