# Glider Documentation System Implementation Plan

> For Hermes: use the markdown-first workflow, progressive disclosure, and beans to roll this out in small independent tasks.

## Goal

Establish `docs/glider/` as the home for a reusable planning system that defines workflow, layered documentation, and agent execution expectations.

## Architecture

Glider should be a documentation framework, not a plugin system. `AGENTS.md` remains the small global entry point. `docs/glider/` becomes the focused process and design area that explains how initiatives are shaped, decomposed, and executed through linked markdown docs and beans.

## Scope

This plan covers:
- the workflow model
- the layered documentation system design
- the minimum agent skills and planning assets required to operate the model
- the phased rollout needed to make Glider usable across projects

## Deliverables

- `docs/glider/README.md`
- `docs/glider/workflow.md`
- `docs/glider/layered-documentation-system.md`
- `docs/glider/agent-skills-and-plans.md`
- follow-up initiative templates under `docs/glider/projects/` or another approved structure

## Phase 1: Establish the core Glider docs

Objective:
Create the core process documents so agents and humans share one consistent operating model.

Completion criteria:
- the Glider index exists
- workflow, documentation-layer, and skills docs exist
- docs indexes point to Glider
- the decision is recorded

## Phase 2: Create reusable initiative scaffolding

Objective:
Provide reusable markdown templates for initiative, phase, and task bundles.

Planned outputs:
- initiative README template
- idea template
- discussion template
- research template
- MVP template
- phase template
- task discussion template
- task research template
- task plan template

Completion criteria:
- each template maps to a specific layer in the Glider system
- templates are cross-linked and easy to instantiate for a new project
- template usage guidance is documented

## Phase 3: Add Glider execution conventions

Objective:
Make execution predictable across tasks and agents.

Planned outputs:
- bean/body conventions for task linkage
- verification and closure checklist
- optional review checkpoints for implementation tasks

Completion criteria:
- task beans follow one predictable shape
- doc linkage expectations are explicit
- completion and drift-prevention rules are documented

## Phase 4: Optional automation and skills

Objective:
Add specialized skills only after the markdown workflow is stable.

Potential follow-up work:
- scaffolding skill for Glider initiative/task bundles
- doc audit skill for missing links or missing required artifacts
- bean/doc consistency validator

Completion criteria:
- any automation supports the markdown system rather than replacing it
- no automation becomes a hidden source of truth

## Task Breakdown Strategy

Use the following kinds of beans:
- one feature or task bean for each Glider rollout slice
- optional parent bean for the overall Glider initiative
- one bean per template pack or audit enhancement when work is independent

Each execution bean should link to:
- the relevant Glider docs
- the parent initiative or phase docs
- the exact task plan used for implementation

## Success Metrics

Glider is successful when:
- a new project can be started from idea to bean-ready tasks using only markdown docs and beans
- agents can discover the right docs with one or two retrieval hops
- task plans are specific enough to reduce implementation drift
- the system remains readable without plugin-specific tooling

## Immediate Follow-up Recommendation

Next, create the Phase 2 template pack inside the Glider area so the workflow can be reused instead of rewritten for every initiative.
