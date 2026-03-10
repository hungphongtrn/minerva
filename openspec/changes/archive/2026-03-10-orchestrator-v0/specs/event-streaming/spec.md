## ADDED Requirements

### Requirement: Runs stream events over SSE
The system SHALL provide an SSE endpoint per run that streams structured JSON events suitable for UI rendering.

#### Scenario: Client receives streamed events
- **WHEN** a client subscribes to a run's SSE endpoint
- **THEN** the client receives a sequence of JSON events as the run progresses

### Requirement: SSE events include stable metadata
Each SSE event MUST include at least: `type`, `run_id`, `ts` (timestamp), and a monotonically increasing `seq` number.

#### Scenario: Event sequence is ordered
- **WHEN** a run emits multiple events
- **THEN** each successive event has a `seq` greater than the previous event

### Requirement: Agent events are forwarded with minimal transformation
The system SHALL forward the pi-agent-core lifecycle and message events to SSE with minimal transformation.

#### Scenario: message_update text deltas are streamed
- **WHEN** the agent produces a streaming assistant response
- **THEN** the SSE stream includes events that represent the incremental message updates

### Requirement: Tool execution events are streamed
The system SHALL stream tool execution lifecycle events including start, incremental updates, and end.

#### Scenario: Tool progress appears in SSE
- **WHEN** a tool executes and produces streaming output
- **THEN** the SSE stream includes tool execution update events during execution

### Requirement: SSE stream terminates at run completion
The system SHALL close the SSE stream after the run reaches a terminal state.

#### Scenario: Stream closes after terminal state
- **WHEN** a run completes, fails, or is cancelled
- **THEN** the SSE connection is closed by the server
