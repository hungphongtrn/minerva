# Markdown-First Workflow with Beans

This project does not depend on specification plugins. The source of truth is:

- `AGENTS.md` for universal operating rules and document navigation
- focused markdown documents under `docs/` for discussion, research, design, plans, and technical reference
- beans for issue tracking and execution status

## Core Rules

1. Start from plain markdown, not plugin-managed specs.
2. Use progressive disclosure: small index docs pointing to focused detail docs.
3. Track every executable task with a bean.
4. Keep documents and beans linked so context is recoverable without chat history.
5. Prefer small, independent tasks that can be executed and verified without waiting on unrelated work.

## Delivery Loop

### 1. Start with an idea

Capture the initial concept in a focused markdown document under `docs/`.

Recommended outputs:
- a project or feature idea note
- the problem statement
- target users and constraints

### 2. Discuss + research + interview to shape an MVP

Turn the raw idea into an MVP through iterative conversation, investigation, and agent-led questioning.

Required outputs:
- discussion document: decisions, open questions, assumptions, rejected directions
- research document: references, examples, tradeoffs, competitive or technical findings
- MVP document: clear scope, success criteria, non-goals, and risks

### 3. Repeat the loop to break the MVP into executable phases

Each phase should be testable and reviewable on its own.

Required outputs per phase:
- phase document linked from the MVP doc
- acceptance criteria
- dependencies and sequencing notes
- evidence of why the phase boundary is correct

### 4. Repeat the loop again until work is broken into tasks

Tasks are the execution unit.

A task is ready only when it is:
- independent or explicitly unblocked
- bite-sized
- testable
- linked to the higher-level phase and MVP docs
- backed by enough discussion and research for low-drift execution

## Required Task Bundle

Every task bean must point to a markdown document bundle that contains or links to:

1. Discussion document
   - what was decided
   - unresolved questions
   - edge cases and constraints

2. Research document
   - source material
   - technical validation
   - tradeoffs and rationale

3. Higher-layer project document
   - parent MVP, phase, or architecture doc
   - why this task exists

4. Execution plan document
   - exact objective
   - files or systems expected to change
   - implementation steps
   - test/verification steps
   - rollback or correction notes when useful

The execution plan is mandatory because it reduces drift and makes completion criteria explicit.

## Bean Requirements

Each executable task maps to one bean.

Bean expectations:
- title states the concrete outcome
- body includes a checklist of the remaining work
- links to the discussion, research, parent, and execution-plan docs
- status reflects reality
- summary of changes is added before marking complete

Use parent beans for higher layers such as milestones, epics, or features when helpful, but execution still happens through small task beans.

## Suggested Document Layout

```text
docs/
  INDEX.md
  project/
    INDEX.md
    idea-name/
      INDEX.md               <- index for the initiative
      mvp.md
      research.md
      discussion.md
      phases/
        INDEX.md
        phase-1.md
      tasks/
        INDEX.md
        task-001-plan.md
        task-001-research.md
        task-001-discussion.md
  process/
    INDEX.md
    markdown-beans-workflow.md
```

Adjust the folder names to fit the project, but preserve the pattern:
small indexes, focused docs, explicit links.

## Definition of Ready for a Task

A task can start when:
- the bean exists
- the task is not blocked
- the linked docs are present
- the execution plan is specific enough to verify completion
- the task can be completed in a small, reviewable slice

## Definition of Done for a Task

A task is done when:
- implementation matches the execution plan or the plan is updated with the approved deviation
- tests or other verification steps are recorded
- affected docs are updated
- the bean checklist is fully checked off
- the bean includes a summary of changes

## Role of AGENTS.md

`AGENTS.md` stays small. It should:
- point to the most important docs
- define universal rules
- avoid storing large task-specific details

Detailed process knowledge belongs in `docs/process/` and task-specific materials belong near the relevant project docs.

## Bottom Line

Use AGENTS.md for navigation, markdown docs for context, and beans for execution tracking. No specification plugins are required.
