# Glider Layered Documentation System

## Purpose

Define a layered markdown system that keeps `AGENTS.md` small while preserving enough structure for reliable execution.

## Layer Model

### Layer 0: Global operating rules

Primary artifact:
- `AGENTS.md`

Contains only:
- universal project rules
- navigation to the most important docs
- global process expectations
- commit and decision-log requirements

Must not contain:
- long feature-specific plans
- bulky research notes
- one-off task details

### Layer 1: Shared process and project anchors

Primary artifacts:
- `docs/README.md`
- `docs/process/README.md`
- `docs/process/markdown-beans-workflow.md`
- `docs/PROJECT.md`
- `docs/ROADMAP.md`
- `docs/DECISIONS.md`

Purpose:
- define how work is organized
- define product scope and rollout direction
- preserve cross-project rules and decisions

### Layer 2: Initiative index

Primary artifact:
- `docs/glider/projects/<initiative>/README.md`

Purpose:
- provide the map for a single initiative
- link to idea, MVP, research, discussion, phases, tasks, and related beans
- keep the first retrieval hop small and obvious

### Layer 3: Initiative shaping docs

Artifacts:
- `idea.md`
- `discussion.md`
- `research.md`
- `mvp.md`

Purpose:
- turn a concept into a bounded initiative
- preserve rationale before execution begins

### Layer 4: Phase docs

Artifacts:
- `phases/README.md`
- `phases/phase-<nn>.md`

Purpose:
- define executable slices of the MVP
- explain sequencing and testability
- bound task creation within each phase

### Layer 5: Task bundle

Artifacts:
- `tasks/task-<nnn>-discussion.md`
- `tasks/task-<nnn>-research.md`
- `tasks/task-<nnn>-plan.md`
- bean file under `.beans/`

Purpose:
- provide enough local context for implementation
- make each task independently understandable and reviewable

## Folder Design

```text
docs/
  glider/
    README.md
    implementation-plan.md
    workflow.md
    layered-documentation-system.md
    agent-skills-and-plans.md
    projects/
      <initiative>/
        README.md
        idea.md
        discussion.md
        research.md
        mvp.md
        phases/
          README.md
          phase-01.md
        tasks/
          README.md
          task-001-discussion.md
          task-001-research.md
          task-001-plan.md
```

## Navigation Rules

- Every directory with multiple documents should have a `README.md` index.
- Every task plan should link upward to its phase, MVP, and initiative index.
- Every initiative README should link downward to the current active phases and task bundles.
- Beans should link to the relevant task bundle and parent docs.

## Document Responsibilities

- discussion docs record decisions, concerns, and unresolved questions
- research docs record evidence, references, and tradeoffs
- MVP and phase docs define scope and sequencing
- task plans define exact execution and verification steps
- decision log entries record meaningful approved direction changes

## Drift Prevention Rules

To prevent project drift:
- never execute a task without a task plan
- never close a bean without updating affected docs
- never rely on chat history as the only source of rationale
- prefer linking to a source doc instead of duplicating content across layers
