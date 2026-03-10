# Wind-Harvester Improvements

Implement all gaps identified in the analysis: commit integration (A), session context (D), bootstrap flow (G+H), loop boundaries (B), status command (E), doc living sync (I), and beans-openspec sync (C). All changes are scoped to `wind-harvester/src/`.

> [!IMPORTANT]
> The installer (`bin/install.js`) auto-discovers all files under `src/command/`, `src/skills/`, and `src/windmill/` and copies them to the target. New files are automatically included — **no installer changes needed**. The `{{WINDMILL_ROOT}}` and `{{SKILL_ROOT}}` placeholders are rewritten at install time.

## Proposed Changes

### Component 1: Bootstrap (Proposals G + H)

New windmill reference docs, templates, command, and skill for project initialization.

---

#### [NEW] [overview.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/bootstrap/overview.md)

Bootstrap workflow overview:
- When to use (new project or joining existing)
- Greenfield vs. brownfield modes
- Prerequisites: user has filled project docs using templates
- The bootstrap sequence: validate docs → init openspec → init beans → create milestones → create epics → hint next step

#### [NEW] [doc-templates.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/bootstrap/doc-templates.md)

Template rules:
- Fixed set of 5 docs: project, architecture, coding-standards, roadmap, research
- Folder-first convention: always `docs/<topic>/README.md`, never `docs/TOPIC.md`
- Growth rules: >300 lines or >5 sections triggers decomposition
- Decomposition pattern: README.md becomes index, sub-files hold content, entry-point path is stable
- Reference links must always point to `README.md` (stable entry point)

#### [NEW] [milestone-creation.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/bootstrap/milestone-creation.md)

Rules for converting `docs/roadmap/README.md` into Beans milestones:
- Each `## Phase` section becomes a milestone
- Each bullet under a phase becomes an epic
- Milestones are ordered by dependency
- Bean CLI commands for milestone/epic creation

#### [NEW] Templates (5 files)

| Template file | Target |
|--------------|--------|
| `bootstrap/templates/project/README.md.tmpl` | `docs/project/README.md` |
| `bootstrap/templates/architecture/README.md.tmpl` | `docs/architecture/README.md` |
| `bootstrap/templates/coding-standards/README.md.tmpl` | `docs/coding-standards/README.md` |
| `bootstrap/templates/roadmap/README.md.tmpl` | `docs/roadmap/README.md` |
| `bootstrap/templates/research/README.md.tmpl` | `docs/research/README.md` |

Each template contains section headers with guidance comments (`<!-- Fill: ... -->`) and follows the folder-first convention. Templates ship in wind-harvester but are **not** installed to `.opencode/` — they're copied to `docs/` by the bootstrap command.

#### [NEW] [bootstrap.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/command/bootstrap.md)

Command entry point (`/harvest-bootstrap`):
- Description: Initialize project with OpenSpec, Beans, and milestones from project docs
- References windmill bootstrap docs
- Steps:
  1. Check if docs exist (validate minimum: project, architecture, roadmap)
  2. Init openspec if `openspec/config.yaml` doesn't exist
  3. Init beans if `.beans.yml` doesn't exist
  4. Parse `docs/roadmap/README.md` → create milestones + epics
  5. Hint: suggest `/opsx:new` or `/opsx:propose` for first change
- Guardrails: idempotent, don't recreate existing milestones
- Ends with standard hint block

#### [NEW] [SKILL.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/skills/harvest/harvest-bootstrap/SKILL.md)

Thin skill entry point for bootstrap. References windmill bootstrap docs.

---

### Component 2: Commit Skill (Proposal A)

New skill and windmill reference docs for per-bean commits.

---

#### [NEW] [commit-rules.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/commit/commit-rules.md)

Overview:
- When to commit: after each bean's work is complete, before tagging
- General format: conventional commits with `Refs: <bean-id>` footer
- One commit per bean (atomic)
- Reference `docs/COMMIT_GUIDELINES.md` for full conventional commit spec
- Links to sub-docs for each command type

#### [NEW] [plan-commits.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/commit/plan-commits.md)

Format for `/harvest-plan` commits:
- Type: `docs(plans)`
- Subject: `create plan for <bean-title>`
- Body: what the plan covers, key decisions
- Footer: `Refs: <bean-id>`
- Example commit

#### [NEW] [implementation-commits.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/commit/implementation-commits.md)

Format for `/harvest-implement` commits:
- Type: `feat`, `fix`, or `refactor` (based on bean type)
- Scope: derived from changed module/layer
- Subject: imperative, ≤50 chars
- Body: what changed and why
- Footer: `Refs: <bean-id>`
- Granularity rules from `COMMIT_GUIDELINES.md` (isolate refactoring, separate config, single layer)
- Example commits for each type

#### [NEW] [verification-commits.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/commit/verification-commits.md)

Format for `/harvest-check` commits:
- Verification notes: `docs(verify): add verification notes for <bean-title>`
- Fix bean creation: `chore(harvest): create fix bean for <bean-title>`
- Footer: `Refs: <bean-id>`
- Example commits

#### [NEW] [SKILL.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/skills/harvest/harvest-commit/SKILL.md)

Thin skill entry point:
- When to invoke: after completing work in any `/harvest-*` command
- References `{{WINDMILL_ROOT}}/commit/commit-rules.md`
- Links to specific sub-docs based on command context

---

### Component 3: Session Context (Proposal D)

New windmill doc specifying the `.harvest-state.json` format.

---

#### [NEW] [session-state.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/session-state.md)

Specification:
- Location: `openspec/changes/<name>/.harvest-state.json`
- Schema (JSON with fields: change, epicBean, fixIterations, userDecisions, lastCommand, lastCommandAt)
- Read rules: each command reads on entry, skips if missing (first run)
- Write rules: each command updates after completing work
- User decisions: stored when escalation options are presented
- Used by `/harvest-status` for dashboard data

---

### Component 4: Update Existing Commands

Add commit skill reference, hint blocks, and fresh context guidance to all three commands.

---

#### [MODIFY] [plan.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/command/harvest/plan.md)

Changes:
- Add commit skill reference line at top of steps section
- Add session state read/write to steps
- Replace step 5 with standard hint block (done summary + next steps + context files)
- Add fresh context guidance

#### [MODIFY] [implement.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/command/harvest/implement.md)

Changes:
- Add commit skill reference line at top of steps section
- Add session state read/write to steps
- Add per-bean commit step (after implementation, before tagging)
- Replace step 5 with standard hint block
- Add fresh context guidance

#### [MODIFY] [check.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/command/harvest/check.md)

Changes:
- Add commit skill reference line at top of steps section
- Add session state read/write to steps
- Add doc drift check hint after all verifications pass
- Replace step 5 with standard hint block (includes doc sync suggestion)
- Add fresh context guidance
- Reference `workflow/loop-boundaries.md` for escalation decisions

---

### Component 5: Loop Boundaries (Proposal B)

---

#### [NEW] [loop-boundaries.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/loop-boundaries.md)

Decision heuristics for the agent to present to the user:
- 5 scenarios (simple bug, spec change needed, scope creep, repeated failure, deferred beans)
- Each with: condition, recommended action, analysis to present, rationale
- Agent always presents options and waits — never decides autonomously
- Format: numbered options with pros/cons for user to choose

---

### Component 6: Status Command (Proposal E)

---

#### [NEW] [status.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/command/harvest/status.md)

Command entry point (`/harvest-status`):
- Read-only dashboard, no mutations
- Reads `.harvest-state.json` + queries beans by tags
- Output format defined in `status-format.md`

#### [NEW] [SKILL.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/skills/harvest/harvest-status/SKILL.md)

Thin skill entry point for status display.

#### [NEW] [status-format.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/status-format.md)

Dashboard format:
- Change name + epic bean
- Per-state counts (verified, implemented, planned, unplanned, fix beans)
- Fix iteration tracker
- Last action + suggested next step
- File links to relevant plans and state file

---

### Component 7: Doc Living Sync (Proposal I)

---

#### [NEW] [doc-sync.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/doc-sync.md)

Post-archive doc drift checking:
- When to run: after all beans verified, before suggesting `/opsx-archive`
- Drift categories: addition, contradiction, deprecation, growth
- Actions per category
- Commit format: `docs(<scope>): sync <doc> with <change> implementation`
- Agent presents drift findings, user decides what to update

---

### Component 8: Beans ↔ OpenSpec Sync (Proposal C)

---

#### [NEW] [sync-rules.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/sync-rules.md)

Rules for syncing bean state back to OpenSpec:
- Update `tasks.md` checkboxes to match verified beans
- Append implementation notes section to `design.md` on divergences
- When to run: alongside doc drift check, pre-archive

---

### Housekeeping

#### [MODIFY] [README.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/README.md)

Update to reflect new directory structure (bootstrap, commit sections).

#### [MODIFY] [overview.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/workflow/overview.md)

Update pipeline to include: bootstrap entry point, commit steps, doc sync, and status command.

#### [MODIFY] [coder-prompts.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/implementation/coder-prompts.md)

Add commit step to the prompt template and fresh context note.

#### [MODIFY] [escalation.md](file:///Users/phong/Workspace/minerva/wind-harvester/src/windmill/harvest/verification/escalation.md)

Reference `workflow/loop-boundaries.md` for detailed decision heuristics.

#### [MODIFY] [README.md](file:///Users/phong/Workspace/minerva/wind-harvester/README.md)

Update contents list to reflect new commands and skills.

---

## Verification Plan

### Automated Tests

Wind-harvester is a pure markdown/docs package with no existing test suite. Verification is structural:

```bash
# 1. Verify all new files exist under src/
find wind-harvester/src -name "*.md" -o -name "*.tmpl" | sort

# 2. Run installer dry-run to verify all files are discovered
node wind-harvester/bin/install.js --target local --scope all --force --cwd /tmp/wh-test

# 3. Verify placeholder rewriting works for new files
grep -r "{{WINDMILL_ROOT}}" /tmp/wh-test/.opencode/ && echo "FAIL: unrewritten placeholders" || echo "PASS"
grep -r "{{SKILL_ROOT}}" /tmp/wh-test/.opencode/ && echo "FAIL: unrewritten placeholders" || echo "PASS"

# 4. Verify no broken internal links (references between windmill docs)
grep -roh '`{{WINDMILL_ROOT}}/[^`]*`' wind-harvester/src/ | sort -u
# Manually check each referenced path exists in src/windmill/harvest/
```

### Manual Verification

1. **Structure check**: Run `find wind-harvester/src -type f | sort` and verify it matches the file list in this plan
2. **Cross-reference check**: Open each command file and verify every `{{WINDMILL_ROOT}}/...` reference points to an existing windmill doc
3. **Template review**: Open each `.tmpl` file and verify it follows the folder-first convention with guidance comments
4. **Hint block consistency**: Open all 4 command files (plan, implement, check, bootstrap) and verify each ends with the standard `✅ Done` / `🔜 Next Steps` / `📎 Context Files` hint block format
5. **Commit skill reference**: Verify all 3 existing commands (plan, implement, check) include the commit skill reference line
