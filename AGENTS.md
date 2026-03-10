# AGENTS.md

## Beans as our issue trackers

- **IMPORTANT**: before you do anything else, run the `beans prime` command and heed its output. 
- Terminology: a bean = a issue
- **OpenSpec Rule**: When working with any `openspec-*` command, always create a bean to track the change. Every OpenSpec change should be properly documented and tracked through a bean.

## Docs TOC

- `docs/README.md`: documentation entry point (index)
- `docs/PROJECT.md`: what Minerva is building (phase focus, scope)
- `docs/ROADMAP.md`: phased delivery plan
- `docs/CODING_STANDARDS.md`: coding quality and architecture dependency rules
- `docs/architecture/README.md`: architecture index
- `docs/architecture/agent-runtime-v0.md`: orchestrator + Daytona sandbox notes (v0)
- `docs/research/pi-agent-core/README.md`: pi-agent-core overview
- `docs/research/pi-agent-core/events.md`: pi-agent-core event model (maps well to SSE)

## Documentation Guidelines

**IMPORTANT**: All documentation MUST be placed in `/Users/phong/Workspace/minerva/docs/` directory.

### Keep Docs In Sync

When we discuss, design, or implement changes, we must also update the relevant documents in `docs/` (and add new docs/index entries when needed). Prefer small, focused docs and link them from an index (progressive disclosure).

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

## Coding Standards Reference

Coding quality and architecture rules are maintained in `docs/CODING_STANDARDS.md`.

## Code Commits

- After each completed bean, commit it following `docs/COMMIT_GUIDELINES.md`, include the relevant bean IDs in the commit message.
