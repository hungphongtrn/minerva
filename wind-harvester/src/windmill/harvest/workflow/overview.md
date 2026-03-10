# Harvest Workflow Overview

The harvest workflow turns OpenSpec changes into tracked, planned, implemented, and verified beans.

## Pipeline

1. `/harvest-plan` discovers unplanned work or creates it from `tasks.md`.
2. `/harvest-implement` executes planned work by priority tier.
3. `/harvest-check` verifies completed work and creates fix beans when needed.
4. After all beans verify, the change can move to the normal archive flow.

## Progressive Disclosure

- Commands stay short and only describe orchestration.
- Skills stay short and only describe when to invoke the agent.
- Detailed parsing rules, prompt templates, and bean body formats live in the focused docs next to this file.
