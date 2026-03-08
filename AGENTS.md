# AGENTS.md

## Documents

### Project Documentation
- **[Coding Standards](/Users/phong/Workspace/minerva/docs/CODING_STANDARDS.md)** - Code style and standards
- **[Architecture Overview](/Users/phong/Workspace/minerva/docs/architecture/README.md)** - System architecture and components
- **[State Machines](/Users/phong/Workspace/minerva/docs/architecture/state-machines.md)** - All state diagrams
- **[Execution Flow](/Users/phong/Workspace/minerva/docs/architecture/execution-flow.md)** - Request flow documentation
- **[Component Catalog](/Users/phong/Workspace/minerva/docs/architecture/component-catalog.md)** - Component reference
- **[Dead Code & Legacy](/Users/phong/Workspace/minerva/docs/architecture/dead-code-legacy.md)** - Cleanup opportunities

## Documentation Guidelines

**IMPORTANT**: All documentation MUST be placed in `/Users/phong/Workspace/minerva/docs/` directory.

### Progressive Disclosure Principle

For large or complex documentation, always follow progressive disclosure:

1. **Break down into smaller files** - Create focused documents (e.g., `state-machines.md`, `execution-flow.md`)
2. **Use index/moc/toc** - Create a README or index file that links to all related docs
3. **Cross-reference with links** - Use relative links between documents
4. **Avoid monolithic files** - Keep files under 500 lines when possible

**Example structure:**
```
docs/
├── README.md                 # Main entry point with links
├── architecture/
│   ├── README.md            # Architecture overview (index)
│   ├── state-machines.md    # State diagrams
│   ├── execution-flow.md    # Execution flows
│   ├── component-catalog.md # Component reference
│   └── dead-code-legacy.md  # Cleanup guide
└── CODING_STANDARDS.md
```

### File Organization Rules

- ✅ **DO** create subdirectories for logical groupings
- ✅ **DO** use README.md as index in each subdirectory
- ✅ **DO** link related documents together
- ✅ **DO** use descriptive filenames
- ❌ **DON'T** create docs in root directory (except README.md)
- ❌ **DON'T** create single monolithic docs >500 lines
- ❌ **DON'T** duplicate content across files

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->
