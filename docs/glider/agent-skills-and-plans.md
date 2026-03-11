# Glider Agent Skills and Plans

## Purpose

Define the minimum agent capabilities and planning assets needed to operate the Glider workflow reliably.

## Required Agent Behaviors

Agents working in Glider should consistently do the following:
- start by checking beans and creating or updating the relevant bean
- use `AGENTS.md` as the entry point, then load only the needed Glider docs
- keep documentation in sync during planning and execution
- maintain progressive disclosure instead of writing one giant planning document
- record user decisions in `docs/DECISIONS.md`
- commit completed bean work with the bean ID in the commit message

## Core Skills to Use

### 1. Writing plans

Use the `writing-plans` skill whenever an initiative, phase, or task needs a multi-step implementation plan.

Expected outcome:
- small executable steps
- explicit file targets
- verification steps
- a plan that minimizes ambiguity for future execution

### 2. Subagent-driven development

Use `subagent-driven-development` when a plan is ready and execution should happen task-by-task with isolated context.

Expected outcome:
- one execution unit per task bean
- reduced context pollution
- easier review and recovery when a task fails

### 3. Test-driven development

Use `test-driven-development` for implementation tasks that introduce or change behavior.

Expected outcome:
- failing test first when practical
- minimal implementation
- passing verification before closure

### 4. Requesting code review

Use `requesting-code-review` after meaningful implementation work or before merging risky changes.

Expected outcome:
- explicit review checkpoint
- stronger alignment with documented plans and standards

## Planning Assets Glider Needs

### Initiative-level assets
- initiative README/index
- idea doc
- discussion doc
- research doc
- MVP doc

### Phase-level assets
- phases README/index
- one doc per phase with objectives, dependencies, and acceptance criteria

### Task-level assets
- task discussion doc
- task research doc
- task execution plan doc
- bean

## Plan Taxonomy

Use these plan types:

1. system plan
   - defines the overall workflow or architecture for a domain
2. initiative plan
   - defines the rollout of a specific product or feature initiative
3. phase plan
   - defines a bounded delivery slice
4. task plan
   - defines exact implementation and verification steps for one bean

## Skill Gaps to Fill Later

The initial Glider workflow can operate with existing skills, but future dedicated skills may help:
- a Glider planning skill that scaffolds initiative/phase/task docs
- a Glider doc-audit skill that checks required links across layers
- a Glider bean-sync skill that validates bean/doc consistency

These are optional enhancements, not prerequisites for starting Glider.
