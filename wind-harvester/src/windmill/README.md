# Windmill

`windmill` is the shared reference layer for packaged harvest assets.

- `harvest/workflow/`: pipeline overview and tag state machine
- `harvest/bootstrap/`: bootstrap flow, doc template rules, and roadmap-to-milestone mapping
- `harvest/commit/`: per-command commit formats and commit timing rules
- `harvest/planning/`: task parsing, bean creation, planner prompts, plan templates
- `harvest/implementation/`: execution model and coder prompts
- `harvest/verification/`: verification checks, fix bean rules, escalation

Commands and skills should stay thin and point here for deeper guidance.
