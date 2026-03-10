## ADDED Requirements

### Requirement: Runs have a lifecycle with stable identifiers
The system SHALL create a unique `run_id` for each run and associate it with a `user_id`.

#### Scenario: Starting a run returns a run_id
- **WHEN** a user starts a run
- **THEN** the system returns a new `run_id` associated with that `user_id`

### Requirement: Runs are serialized per user
The system MUST ensure at most one run is actively executing for a given `user_id` at a time.

#### Scenario: Second run is queued while first is running
- **WHEN** a user starts a second run while a prior run for the same `user_id` is executing
- **THEN** the second run is placed in a queued state until the first run completes or is cancelled

### Requirement: Runs are cancellable
The system SHALL allow a user to cancel an in-progress run.

#### Scenario: Cancelling a run stops execution
- **WHEN** a user requests cancellation for an active run
- **THEN** the system aborts the agent loop and stops any in-flight tool execution
- **AND THEN** the run transitions to a cancelled terminal state

### Requirement: Runs can enforce timeouts
The system SHALL support timeouts at least at the run level and the tool-execution level.

#### Scenario: Run timeout produces a terminal failure state
- **WHEN** a run exceeds its configured timeout
- **THEN** the system aborts the run
- **AND THEN** the run transitions to a failed terminal state with a timeout reason

### Requirement: Disconnecting from SSE does not implicitly cancel a run
The system SHALL continue running a run even if the SSE client disconnects.

#### Scenario: Run continues after SSE disconnect
- **WHEN** a client disconnects from the SSE stream during a run
- **THEN** the run continues until it reaches a terminal state unless explicitly cancelled
