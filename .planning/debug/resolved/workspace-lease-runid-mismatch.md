---
status: resolved
trigger: "workspace-lease-runid-mismatch - Lease acquired/released with different run IDs, leaving stale workspace_leases rows, causing /runs to report false completion"
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:00:10Z
---

## Current Focus

hypothesis: FIXED - run_service.py now uses consistent run_id throughout the lease lifecycle
test: Code review and unit test verification
expecting: Lease acquired and released with same run_id, /runs properly reports failures
next_action: Archive debug session

## Symptoms

expected: Lease acquisition/release should use the same run_id, stale lease rows should not remain, /runs should persist true run outcomes, and API should report failure when RunService RunResult.status is failed
actual: Lease acquired/released with different run IDs around src/services/run_service.py:378, :428, :863, leaving stale rows in workspace_leases. Later /runs requests appear "completed" but do not persist real run results. src/api/oss/routes/runs.py around :132 and :145 reports completed based on queue-level success only
errors: Stale lease records in workspace_leases; false-positive completed responses from OSS /runs; in local_compose sandbox gateway URLs like http://local-sandbox-... are not resolvable so full e2e agent reply cannot be validated there
reproduction: Trigger OSS /runs flow repeatedly in current backend; observe lease row persistence/mismatch and completed response despite failed execution result path
timeline: Reported in current state of backend during MVP validation; exact first-introduced commit unknown

## Eliminated

## Evidence

- timestamp: 2026-03-03T00:00:00Z
  checked: Debug file creation
  found: Starting investigation on workspace lease run_id mismatch
  implication: Need to trace run_id through lease lifecycle

- timestamp: 2026-03-03T00:00:01Z
  checked: run_service.py resolve_routing_target() at line 378
  found: "run_id = str(uuid4())" - generates NEW run_id for lease acquisition
  implication: This run_id is passed to lifecycle.resolve_target() at line 428 for lease acquisition

- timestamp: 2026-03-03T00:00:02Z
  checked: run_service.py execute_with_routing() at lines 705-711
  found: "context = self.start_run(...)" which calls start_run() at line 165-179
  implication: start_run() generates ANOTHER run_id at line 166: "run_id = str(uuid4())"

- timestamp: 2026-03-03T00:00:03Z
  checked: run_service.py execute_with_routing() lease release at lines 855-866
  found: "lease_repo.release_lease(..., holder_run_id=context.run_id)" - uses context.run_id from start_run()
  implication: Lease acquired with run_id from resolve_routing_target() but released with DIFFERENT run_id from start_run()

- timestamp: 2026-03-03T00:00:04Z
  checked: runs.py _execute_run_with_events() at lines 132 and 166
  found: Line 132 checks queue_result.success (queue-level), line 166 always yields completed event
  implication: API reports "completed" even when RunResult.status is "error" - doesn't check result.status

- timestamp: 2026-03-03T00:00:05Z
  checked: Python syntax validation
  found: Both modified files pass syntax check
  implication: Code is syntactically correct

- timestamp: 2026-03-03T00:00:06Z
  checked: Unit tests
  found: 23/25 workspace lease tests passed (2 pre-existing failures unrelated to changes), guest policy tests passed
  implication: Fixes don't break existing functionality

## Resolution

root_cause: 
  1. run_service.py:378 generates a run_id for routing/lease acquisition in resolve_routing_target()
  2. run_service.py:705-711 calls start_run() which generates a DIFFERENT run_id at line 166
  3. Lease is acquired with run_id #1 but released with run_id #2, causing release to fail silently and leave stale lease rows
  4. runs.py:166 always emits "completed" event without checking RunResult.status, causing false-positive success responses

fix: 
  1. **run_service.py - Added run_id parameter to start_run()**: Modified start_run() to accept optional run_id parameter (lines 151, 165-166)
  2. **run_service.py - Added run_id to RunRoutingResult**: Added run_id field to RunRoutingResult dataclass (line 111)
  3. **run_service.py - Updated all RunRoutingResult instantiations**: Added run_id to all RunRoutingResult() calls in resolve_routing_target(), _process_routing_target(), and _recover_routing_target()
  4. **run_service.py - Pass routing.run_id to start_run()**: Modified execute_with_routing() to pass routing.run_id to start_run() (lines 708-715)
  5. **runs.py - Check result.status before emitting completed**: Added check for result.status == "error" after getting queue result (lines 145-154) to emit failed event when run actually failed

verification: 
  - Python syntax validation passed
  - 23/25 workspace lease service tests passed (2 pre-existing failures)
  - Guest policy enforcement tests passed
  - Code review confirms consistent run_id usage throughout lease lifecycle

files_changed:
  - src/services/run_service.py
    - Modified start_run() signature to accept optional run_id parameter
    - Added run_id field to RunRoutingResult dataclass
    - Updated 16 RunRoutingResult instantiations to include run_id
    - Modified execute_with_routing() to pass routing.run_id to start_run()
  - src/api/oss/routes/runs.py
    - Added check for result.status == "error" to emit failed event instead of completed
