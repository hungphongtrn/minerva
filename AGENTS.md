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