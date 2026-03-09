## ADDED Requirements

### Requirement: Agent pack has a minimal, file-based format
The system SHALL treat an agent pack as a directory containing `AGENTS.md` and an optional `.agents/skills/` tree.

#### Scenario: Valid agent pack structure is accepted
- **WHEN** a run is started with a reference to an agent pack that contains `AGENTS.md`
- **THEN** the system accepts the pack as valid even if `.agents/skills/` is missing

### Requirement: AGENTS.md drives the system prompt
The system SHALL load `AGENTS.md` from the selected agent pack and use it as the primary system prompt input for the agent loop.

#### Scenario: AGENTS.md is included in the agent context
- **WHEN** the orchestrator starts an agent run
- **THEN** the agent loop context includes the contents of `AGENTS.md` as system prompt material

### Requirement: Skills are loaded as instructional text only (v0)
The system SHALL load `.agents/skills/**/SKILL.md` files as plain text guidance for the agent. Skills MUST NOT introduce new executable capabilities in v0.

#### Scenario: Skills influence guidance but do not add tools
- **WHEN** an agent pack contains multiple `.agents/skills/**/SKILL.md` files
- **THEN** the agent context includes their text content
- **AND THEN** the executable tool surface remains limited to the v0 tools defined by the runtime

### Requirement: Missing required agent pack files are rejected
The system SHALL reject agent pack references that do not contain `AGENTS.md`.

#### Scenario: Pack missing AGENTS.md is rejected
- **WHEN** a run is started with an agent pack reference that does not contain `AGENTS.md`
- **THEN** the run fails fast with a validation error
