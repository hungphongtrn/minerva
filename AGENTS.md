# AGENTS.md

## Beans as our issue trackers

- **IMPORTANT**: before you do anything else, run the `beans prime` command and heed its output. 
- Terminology: a bean = an issue
- We do not depend on specification plugins or `openspec-*` workflows. Use plain markdown documents under `docs/` plus beans for all planning, design, research, and execution tracking.

In this repository, beans serve not only as the issue tracker but also as an issue-centric project memory. Every artifact (discussion, design, execution logs, decisions) must be attached to an issue, making the issue board the control panel of the project.

**Key Principles:**
- **Issues** = units of work
- **Artifacts** = evidence attached to the issue

If done well, opening the board tells you the entire project state.

**Procedure for handling user requests:**
1. Create a bean for every interactive session
2. A successful interaction is proven via newly created/updated documents being linked in the bean issues, not via response.

## Docs TOC

IMPORTANT: keep this section up to date every time a document is created, renamed, moved, or materially updated, but keep it high-level. `docs/INDEX.md` is the detailed documentation index; this section should only list the key anchor docs agents should check first.

- `docs/INDEX.md`: documentation entry point and detailed index
- `docs/PROJECT.md`: product scope, phase focus, and non-goals
- `docs/ROADMAP.md`: phased delivery plan
- `docs/rulebooks/INDEX.md`: operational rulebooks and guidance docs
- `docs/process/INDEX.md`: markdown-first development workflow and document expectations
- `docs/setups/INDEX.md`: setup and troubleshooting guides for external integrations
- `docs/disussions/INDEX.md`: discussion conclusions captured before planning and implementation
- `docs/DECISIONS.md`: rolling decision log for project and user-driven decisions

## Documentation Guidelines

**IMPORTANT**: All documentation MUST be placed in `/Users/phong/Workspace/minerva/docs/` directory.

### Canonical vs Disposable Docs

- **Canonical docs** are the currently approved ground truth for the project. They constrain execution and should stay stable until a proposal is finalized and accepted. Update canonical docs only after the related plan, proposal, or implementation direction has been finished and explicitly ratified.
- **Disposable docs** are supporting artifacts such as plans, proposals, research notes, discussions, migration sketches, and other exploratory material. They can guide work, but they do not override canonical docs and may be replaced, moved, or deleted once their conclusions are promoted.
- If a document is still under review, still being planned, or not yet approved by the user, treat it as disposable and keep it out of canonical architecture/product ground-truth docs.

### Keep Docs In Sync

When we discuss, design, or implement changes, we must also update the relevant documents in `docs/` (and add new docs/index entries when needed). Prefer small, focused docs and link them from an index (progressive disclosure).

Every time a doc is created, renamed, moved, or materially updated:
- update `docs/INDEX.md` if the index should reference it
- update the `## Docs TOC` section in this `AGENTS.md` only if the high-level anchor list should change
- add or update a matching entry in `docs/DECISIONS.md` when the change captures a decision, direction, constraint, or user-requested policy

Every time the user makes a meaningful decision or explicitly approves a direction:
- record it in `docs/DECISIONS.md` in the same work session
- do this even if no code changes are made yet
- include links to the most relevant docs, files, beans, or artifacts touched by that decision
- treat missing decision-log updates as incomplete documentation work

### Decision Log

Create `docs/DECISIONS.md` before recording decisions there, and maintain it gradually as the project and communication with users develop.

Use this format:

```md
# DECISIONS
* {created_date_time}-{decision made}
- {related file link}
- ...
```

Guidelines:
- append new decisions rather than rewriting history unless correcting an obvious mistake
- keep each decision entry concise and specific
- include links to the most relevant files, docs, beans, or artifacts affected by the decision
- update `docs/DECISIONS.md` whenever a meaningful product, architecture, process, or user-requested decision is made
- if the user states a preference, approves an approach, changes a rule, narrows scope, or rejects a direction, log that decision before considering the work complete

### Progressive Disclosure Principle

For large or complex documentation, always follow progressive disclosure:

1. **Break down into smaller files** - Create focused documents (e.g., `state-machines.md`, `execution-flow.md`)
2. **Use index/moc/toc** - Create an INDEX.md or equivalent index file that links to all related docs
3. **Cross-reference with links** - Use relative links between documents
4. **Avoid monolithic files** - Keep files under 500 lines when possible

**Example structure:**
```
docs/
├── INDEX.md                  # Main entry point with links
├── architecture/
│   ├── INDEX.md             # Architecture overview (index)
│   ├── state-machines.md    # State diagrams
│   ├── execution-flow.md    # Execution flows
│   ├── component-catalog.md # Component reference
│   └── dead-code-legacy.md  # Cleanup guide
└── rulebooks/
    ├── INDEX.md
    └── coding-standards.md
```

### File Organization Rules

- ✅ **DO** create subdirectories for logical groupings
- ✅ **DO** use INDEX.md as index in each docs subdirectory
- ✅ **DO** link related documents together
- ✅ **DO** use descriptive filenames
- ❌ **DON'T** create docs in root directory (except INDEX.md and anchor docs like PROJECT.md)
- ❌ **DON'T** create single monolithic docs >500 lines
- ❌ **DON'T** duplicate content across files

## Rulebooks Reference

Operational guidance docs are grouped under `docs/rulebooks/`.

- Coding quality and architecture rules: `docs/rulebooks/coding-standards.md`
- Commit formatting and traceability rules: `docs/rulebooks/commit-guidelines.md`

## Code Commits

- After each completed bean, commit it following `docs/rulebooks/commit-guidelines.md`, include the relevant bean IDs in the commit message.
