# Glider Workflow

## Purpose

Define the default workflow for turning an initial idea into executable, testable task beans with enough documentation to reduce drift.

## Workflow Stages

### 1. Idea capture

Start with a short markdown document that captures:
- problem statement
- target users
- desired outcome
- known constraints
- open questions

Suggested artifact:
- `docs/glider/projects/<initiative>/idea.md`

### 2. Discuss + research + interview into MVP

Use repeated conversation, agent-led questioning, and research to convert the idea into an MVP.

Required outputs:
- `discussion.md`: what was discussed, approved, rejected, and still unknown
- `research.md`: source material, examples, tradeoffs, feasibility notes
- `mvp.md`: scope, success criteria, exclusions, risks, measurable outcomes

Exit criteria:
- the MVP is small enough to ship
- success criteria are testable
- non-goals are explicit

### 3. Break MVP into phases

Decompose the MVP into reviewable slices.

Required outputs per phase:
- phase objective
- entry/exit criteria
- dependency notes
- validation approach
- links back to the MVP and relevant research/discussion docs

Suggested artifact:
- `docs/glider/projects/<initiative>/phases/phase-<nn>.md`

### 4. Break phases into tasks

Each task must be small, independent when possible, and ready for verification.

Required outputs per task:
- discussion doc
- research doc
- execution plan doc
- bean for tracking execution

Suggested artifacts:
- `docs/glider/projects/<initiative>/tasks/task-<nnn>-discussion.md`
- `docs/glider/projects/<initiative>/tasks/task-<nnn>-research.md`
- `docs/glider/projects/<initiative>/tasks/task-<nnn>-plan.md`

### 5. Execute by bean

Execution happens through beans, not through an untracked to-do list.

Each task bean should include:
- links to the higher-layer project and phase docs
- links to the task discussion, research, and plan docs
- a checklist for the implementation work
- verification notes or a linked verification section

### 6. Verify and close

Before marking a bean complete:
- update docs affected by implementation
- record deviations from the plan if they were approved
- add a summary of changes to the bean
- log meaningful decisions in `docs/DECISIONS.md`

## Operating Rules

- If an idea is still vague, stay in discussion/research/interview mode.
- If a phase is too large to test coherently, split it again.
- If a task depends on unresolved discovery, keep it in draft form or as a blocked bean.
- If execution diverges from the plan, update the plan rather than letting the docs drift.

## Minimum Task Readiness Checklist

A task is ready when:
- the problem and expected outcome are clear
- the parent phase and MVP are linked
- the discussion and research docs exist
- the execution plan contains concrete implementation and verification steps
- the bean exists and is not blocked
