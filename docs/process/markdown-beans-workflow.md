# Markdown-First Workflow with Beans

This project does not depend on specification plugins. The source of truth is spread across:

- `AGENTS.md` for universal operating rules and document navigation
- canonical markdown documents under `docs/` for durable product, architecture, API, process, and ratified spec truth
- supporting and evidence markdown documents under `docs/` for planning, research, and discussions
- beans for issue tracking, execution status, and fresh-session operational memory

## Core Rules

1. Start from plain markdown, not plugin-managed specs.
2. Use progressive disclosure: small index docs pointing to focused detail docs.
3. Treat canonical docs as ground truth for execution.
4. Use beans as the operational memory layer for active work.
5. Keep documents and beans linked so context is recoverable without chat history.
6. Prefer small, independent tasks that can be executed and verified without waiting on unrelated work.

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

## Document Authority Model

Treat docs by authority level rather than by detail level alone.

1. Canonical docs
   - `docs/PROJECT.md`, `docs/ROADMAP.md`, `docs/architecture/**`, `docs/api/**`, `docs/process/**`, rulebooks/guidelines docs, and ratified `docs/specs/**`
   - define durable truth used during execution

2. Supporting docs
   - plans, phase breakdowns, migration notes, rollout notes, and draft specs
   - help execute the work but do not override canonical docs

3. Evidence docs
   - research, discussions, comparisons, exploratory notes
   - capture why a direction was chosen but are not authoritative by themselves

If a supporting or evidence doc contains a conclusion that future work must rely on, promote that conclusion into canonical docs and `docs/DECISIONS.md` before closing the bean.

## Task Context Bundle

Every task bean must link to enough context for safe execution and fresh-session recovery.

Required:
1. At least one governing canonical document
   - project, architecture, API, process, or ratified spec docs that constrain the work

2. Bean-local execution state
   - objective
   - current status
   - checklist
   - latest findings
   - next action
   - blockers

Optional when needed:
3. Supporting docs
   - execution plan docs
   - rollout notes
   - larger task or phase breakdowns

4. Evidence docs
   - discussion documents
   - research documents
   - comparison notes

Small tasks can keep the execution plan in the bean body. Medium or large tasks should usually link to a dedicated plan doc.

## Bean Requirements

Each executable task maps to one bean, and each bean acts as the operational memory record for that work.

Create or reuse a bean when:
- the work may continue across sessions
- the work changes repository state
- the work has multiple meaningful steps
- the work may create a durable decision
- the work may need handoff to another session or agent

Bean expectations:
- title states the concrete outcome
- body follows the resumability template or an equivalent high-signal structure
- links to governing canonical docs and any needed supporting or evidence docs
- current status reflects reality, not aspiration
- checklist tracks the remaining execution work
- latest findings and next action are updated before pausing work
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
- the bean exists or the work is still clearly below the bean-creation threshold
- the task is not blocked
- the governing canonical docs are linked or obvious
- the execution plan is specific enough to verify completion, whether in the bean body or a linked plan doc
- the task can be completed in a small, reviewable slice

## Definition of Done for a Task

A task is done when:
- implementation matches the execution plan or the plan is updated with the approved deviation
- tests or other verification steps are recorded
- affected canonical or supporting docs are updated
- durable conclusions have been promoted out of temporary docs and into canonical docs or `docs/DECISIONS.md`
- the bean checklist is fully checked off
- the bean includes a summary of changes
- the bean is left in a state that a fresh reader can understand without the original chat

## Role of AGENTS.md

`AGENTS.md` stays small. It should:
- point to the most important docs
- define universal rules
- avoid storing large task-specific details

Detailed process knowledge belongs in `docs/process/` and task-specific materials belong near the relevant project docs. See also:
- `docs/process/bean-memory-policy.md`
- `docs/process/bean-template.md`

## Bottom Line

Use AGENTS.md for navigation, canonical markdown docs for durable truth, supporting docs for execution context, and beans for execution tracking plus operational memory. No specification plugins are required.
