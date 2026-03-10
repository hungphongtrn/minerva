# Harvest Workflow Overview

The harvest workflow turns OpenSpec changes into tracked, planned, implemented, and verified beans.

## Pipeline

1. `/harvest-bootstrap` seeds docs, initializes tools, and creates roadmap milestones.
2. `/harvest-plan` discovers unplanned work or creates it from `tasks.md`.
3. `/harvest-implement` executes planned work by priority tier and records per-bean commits.
4. `/harvest-check` verifies completed work, creates fix beans when needed, and stops at loop boundaries when user direction is required.
5. `/harvest-status` renders the current dashboard from bean tags and session state.
6. After all beans verify, run doc drift and Beans/OpenSpec sync before the normal archive flow.

## Progressive Disclosure

- Commands stay short and only describe orchestration.
- Skills stay short and only describe when to invoke the agent.
- Detailed parsing rules, prompt templates, and bean body formats live in the focused docs next to this file.
