## MODIFIED Requirements

### Requirement: Runs execute using real LLM provider instead of scripted runtime
The system SHALL execute runs using a configured real model provider via pi-agent-core instead of the scripted event generator.

#### Scenario: Run uses real model for agent loop
- **WHEN** a run is started with a valid agent pack
- **THEN** the system initializes pi-agent-core with the configured model provider
- **AND THEN** the agent loop makes actual LLM calls and processes real responses
- **AND THEN** tool calls from the LLM are executed in the Daytona sandbox

#### Scenario: Run streams real LLM responses
- **WHEN** the LLM generates streaming response content
- **THEN** the system emits SSE events with incremental message updates
- **AND THEN** the events include the actual LLM-generated text

## ADDED Requirements

### Requirement: Run initialization validates provider availability
The system SHALL verify the model provider is healthy before starting a run and fail fast with a clear error if the provider is unavailable.

#### Scenario: Run fails fast when provider is unhealthy
- **WHEN** a run is started and the model provider health check fails
- **THEN** the run fails immediately with a provider error status
- **AND THEN** the error message indicates the provider connectivity issue

### Requirement: Run handles provider errors gracefully
The system SHALL handle provider errors (rate limits, authentication failures, timeouts) and convert them to appropriate run failure states.

#### Scenario: Rate limit error produces clear failure
- **WHEN** the model provider returns a rate limit error during a run
- **THEN** the run transitions to a failed state
- **AND THEN** the error indicates a rate limit was hit

#### Scenario: Provider timeout is handled
- **WHEN** an LLM call exceeds the configured timeout
- **THEN** the system cancels the in-flight request
- **AND THEN** the run transitions to a failed state with timeout reason
