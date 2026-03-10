# Wind-Harvester Improvement Tasks

## P0: Bootstrap & Doc Templates (G+H)
- [ ] Create windmill bootstrap reference docs
  - [ ] `bootstrap/overview.md` — greenfield vs. brownfield, when to use
  - [ ] `bootstrap/doc-templates.md` — template descriptions, growth rules, folder-first convention
  - [ ] `bootstrap/milestone-creation.md` — ROADMAP → Beans milestones rules
- [ ] Create doc templates
  - [ ] `bootstrap/templates/project/README.md.tmpl`
  - [ ] `bootstrap/templates/architecture/README.md.tmpl`
  - [ ] `bootstrap/templates/coding-standards/README.md.tmpl`
  - [ ] `bootstrap/templates/roadmap/README.md.tmpl`
  - [ ] `bootstrap/templates/research/README.md.tmpl`
- [ ] Create bootstrap command: `command/harvest/bootstrap.md`
- [ ] Create bootstrap skill: `skills/harvest/harvest-bootstrap/SKILL.md`

## P0: Commit Skill (A)
- [ ] Create windmill commit reference docs
  - [ ] `commit/commit-rules.md` — overview, when/how to commit
  - [ ] `commit/plan-commits.md` — `docs(plans):` format
  - [ ] `commit/implementation-commits.md` — `feat/fix/refactor:` format
  - [ ] `commit/verification-commits.md` — `docs(verify):` format
- [ ] Create commit skill: `skills/harvest/harvest-commit/SKILL.md`

## P0: Session Context (D)
- [ ] Create session state spec: `workflow/session-state.md`

## P0: Update Existing Commands with Commit + Hints
- [ ] Update [command/harvest/plan.md](file:///Users/phong/Workspace/minerva/.opencode/command/harvest/plan.md) — commit ref, hint block, fresh context
- [ ] Update [command/harvest/implement.md](file:///Users/phong/Workspace/minerva/.opencode/command/harvest/implement.md) — commit ref, hint block, fresh context
- [ ] Update [command/harvest/check.md](file:///Users/phong/Workspace/minerva/.opencode/command/harvest/check.md) — commit ref, hint block, doc drift hint

## P1: Loop Boundaries (B)
- [ ] Create `workflow/loop-boundaries.md` — decision heuristics + escalation options

## P1: Status Command (E)
- [ ] Create `command/harvest/status.md`
- [ ] Create `skills/harvest/harvest-status/SKILL.md`
- [ ] Create `workflow/status-format.md`

## P1: Doc Living Sync (I)
- [ ] Create `workflow/doc-sync.md` — drift categories + post-archive check

## P2: Beans ↔ OpenSpec Sync (C)
- [ ] Create `workflow/sync-rules.md` — tasks.md checkbox sync rules

## Housekeeping
- [ ] Update [windmill/README.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/README.md) — reflect new structure
- [ ] Update [workflow/overview.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/overview.md) — updated pipeline with commit + sync steps
- [ ] Update existing coder/planner prompts for fresh context guidance
- [ ] Update `bin/install.js` — install new files
- [ ] Update [wind-harvester/README.md](file:///Users/phong/Workspace/minerva/wind-harvester/README.md) — updated contents
