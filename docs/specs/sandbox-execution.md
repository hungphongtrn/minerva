# Sandbox Execution

## Purpose

TBD

## Requirements

### Requirement: All tool execution happens inside a Daytona sandbox
The system MUST execute `read`, `write`, and `bash` operations inside a Daytona-provisioned sandbox workspace.

#### Scenario: Tool calls are executed in the sandbox
- **WHEN** the agent issues a tool call for `bash`
- **THEN** the orchestrator executes the command within the Daytona sandbox and not on the host

### Requirement: v0 provides a minimal tool surface
The system SHALL expose exactly the following executable tools in v0: `read`, `write`, and `bash`.

#### Scenario: Unknown tool calls fail deterministically
- **WHEN** the agent requests a tool name outside the v0 tool surface
- **THEN** the system returns a tool error indicating the tool is not available

### Requirement: bash streams output and reports exit status
The `bash` tool SHALL stream stdout/stderr while executing and SHALL report an exit status on completion.

#### Scenario: bash output is streamed to the orchestrator
- **WHEN** `bash` executes a command that emits stdout
- **THEN** the system streams stdout as incremental tool updates
- **AND THEN** the final tool result includes the exit status

### Requirement: File tools are workspace-scoped
The `read` and `write` tools SHALL only access paths within the sandbox workspace root and MUST prevent path traversal.

#### Scenario: Path traversal is rejected
- **WHEN** a `read` tool call attempts to access `../` outside the workspace root
- **THEN** the system rejects the tool call with an error

### Requirement: No long-lived secrets are injected into the sandbox
The system MUST NOT inject long-lived credentials into the sandbox via environment variables or files.

#### Scenario: Tool execution does not require secrets in sandbox
- **WHEN** a run executes `read`, `write`, or `bash`
- **THEN** the sandbox environment does not receive long-lived secrets from the orchestrator

### Requirement: Sandbox outbound network is disabled in v0
The system MUST configure sandboxes so they do not have general outbound network access in v0.

#### Scenario: Network access is unavailable
- **WHEN** `bash` attempts to reach an external host from inside the sandbox
- **THEN** the command fails due to lack of outbound network connectivity
