# Implementation Plan: Orchestrator v0 - Agent Pack Loading

**Bean**: minerva-46a2  
**Scope**: Phase 4.1, 4.2, 4.3  
**Target**: Agent pack validation, skill loading, and system prompt assembly

---

## 1. Problem Statement and Goal

### Problem
Minerva's orchestrator needs to load and validate "agent packs" - a business-friendly format for defining agent behavior. Currently, there is no standardized way to:
1. Validate that an agent pack has the required structure (must include `AGENTS.md`)
2. Load skills from `.agents/skills/**/SKILL.md` files as plain text context
3. Assemble the final system prompt that combines agent identity with skill instructions

The system must handle these operations safely and efficiently while maintaining clear boundaries between validation, loading, and prompt assembly.

### Goal
Create a robust agent pack loading system that:
- Validates agent pack structure and required files
- Loads skills as instructional text (non-executable in v0)
- Assembles a well-structured system prompt for the agent loop
- Provides clear error messages for invalid packs
- Integrates seamlessly with the run orchestration flow

---

## 2. Decision: Architecture Approach

**Decision**: Separate concerns into three distinct layers

1. **Validation Layer**: Checks pack structure and requirements
2. **Loading Layer**: Reads files and extracts content
3. **Assembly Layer**: Combines content into final system prompt

**Rationale**:
- Clear separation enables independent testing of each concern
- Validation can fail fast before expensive I/O operations
- Assembly rules can evolve without changing loading logic
- Skills remain textual-only in v0 (no executable code)

**Agent Pack Structure**:
```
agent-pack/
  AGENTS.md                    # Required: Agent identity / stance / rules
  .agents/
    skills/
      brainstorming/
        SKILL.md               # Instructional content
      planning/
        SKILL.md
      coding/
        SKILL.md
      debugging/
        SKILL.md
      testing/
        SKILL.md
      documentation/
        SKILL.md
```

---

## 3. File-Level Changes

### 3.1 New Files

#### `/services/orchestrator/src/packs/types.ts`
Core domain types for agent packs:
- `AgentPack` - validated pack structure
- `AgentIdentity` - parsed from AGENTS.md
- `Skill` - individual skill with metadata
- `PackValidationResult` - validation outcomes
- `SystemPrompt` - assembled prompt structure

#### `/services/orchestrator/src/packs/validator.ts`
Validation logic:
- `validatePack(path: string): Promise<PackValidationResult>`
- Checks for required `AGENTS.md`
- Validates directory structure
- Reports missing files or invalid formats
- Returns structured error information

#### `/services/orchestrator/src/packs/loader.ts`
File loading operations:
- `loadPack(packPath: string): Promise<AgentPack>`
- `loadSkills(skillsDir: string): Promise<Skill[]>`
- `parseAgentIdentity(content: string): AgentIdentity`
- Reads SKILL.md files as plain text
- Handles file system errors gracefully

#### `/services/orchestrator/src/packs/assembler.ts`
System prompt assembly:
- `assembleSystemPrompt(pack: AgentPack): SystemPrompt`
- Combines identity with skill instructions
- Applies v0 assembly rules (see section 4.3)
- Returns structured prompt with sections

#### `/services/orchestrator/src/packs/errors.ts`
Custom error types:
- `PackValidationError` - structure violations
- `PackNotFoundError` - missing pack
- `MissingRequiredFileError` - missing AGENTS.md
- `SkillLoadError` - file reading failures

#### `/services/orchestrator/src/packs/index.ts`
Public API exports:
- Re-exports all public types and functions
- Main entry point for pack operations

### 3.2 Modified Files

#### `/services/orchestrator/src/types/index.ts`
Add pack-related types to central types module:
- Import and re-export from `src/packs/types.ts`
- Ensure type consistency across services

#### `/services/orchestrator/src/services/run-service.ts`
Integrate pack loading into run creation:
- Accept `packPath` in `CreateRunRequest`
- Call `validatePack()` before creating run
- Load and assemble system prompt
- Pass assembled prompt to agent worker

#### `/services/orchestrator/src/config/index.ts`
Add pack configuration:
- `packs.basePath` - default location for agent packs
- `packs.maxSkillSize` - size limit for skill files (bytes)
- `packs.allowedExtensions` - valid skill file extensions

---

## 4. Key Interfaces and Types

### 4.1 Pack Types

```typescript
// src/packs/types.ts

export interface AgentPack {
  path: string;
  identity: AgentIdentity;
  skills: Skill[];
  metadata: PackMetadata;
}

export interface AgentIdentity {
  name: string;
  description: string;
  stance: string;
  rules: string[];
  rawContent: string;
}

export interface Skill {
  name: string;
  category: string;
  content: string;
  path: string;
  size: number;
}

export interface PackMetadata {
  loadedAt: Date;
  skillCount: number;
  totalSize: number;
}

export interface PackValidationResult {
  valid: boolean;
  errors: PackValidationError[];
  warnings: PackValidationWarning[];
}

export interface SystemPrompt {
  identity: string;
  skills: string;
  assemblyRules: string;
  fullPrompt: string;
  sections: PromptSection[];
}

export interface PromptSection {
  name: string;
  content: string;
  order: number;
}
```

### 4.2 Validation Interface

```typescript
// src/packs/validator.ts

export interface IPackValidator {
  validate(packPath: string): Promise<PackValidationResult>;
  validateSync(packPath: string): PackValidationResult;
}

export class PackValidator implements IPackValidator {
  private requiredFiles: string[] = ['AGENTS.md'];
  
  async validate(packPath: string): Promise<PackValidationResult>;
  validateSync(packPath: string): PackValidationResult;
  
  private checkRequiredFiles(packPath: string): ValidationError[];
  private checkDirectoryStructure(packPath: string): ValidationWarning[];
}
```

### 4.3 Loader Interface

```typescript
// src/packs/loader.ts

export interface IPackLoader {
  load(packPath: string): Promise<AgentPack>;
  loadSkills(skillsDir: string): Promise<Skill[]>;
}

export class PackLoader implements IPackLoader {
  private config: PackLoaderConfig;
  
  constructor(config: PackLoaderConfig);
  
  async load(packPath: string): Promise<AgentPack>;
  async loadSkills(skillsDir: string): Promise<Skill[]>;
  
  private parseIdentity(content: string): AgentIdentity;
  private readSkillFile(path: string): Promise<Skill>;
  private validateSkillSize(size: number): void;
}
```

### 4.4 Assembler Interface

```typescript
// src/packs/assembler.ts

export interface ISystemPromptAssembler {
  assemble(pack: AgentPack): SystemPrompt;
}

export class SystemPromptAssembler implements ISystemPromptAssembler {
  private rules: AssemblyRules;
  
  constructor(rules?: Partial<AssemblyRules>);
  
  assemble(pack: AgentPack): SystemPrompt;
  
  private buildIdentitySection(identity: AgentIdentity): string;
  private buildSkillsSection(skills: Skill[]): string;
  private buildAssemblyRulesSection(): string;
  private orderSkills(skills: Skill[]): Skill[];
}

export interface AssemblyRules {
  identityFirst: boolean;
  includeSkillMetadata: boolean;
  skillOrdering: 'alphabetical' | 'category' | 'size';
  maxPromptLength: number;
}
```

### 4.5 Error Types

```typescript
// src/packs/errors.ts

export class PackError extends Error {
  constructor(message: string, public code: string);
}

export class PackValidationError extends PackError {
  constructor(
    message: string,
    public field: string,
    public severity: 'error' | 'warning'
  );
}

export class PackNotFoundError extends PackError {
  constructor(packPath: string);
}

export class MissingRequiredFileError extends PackValidationError {
  constructor(fileName: string);
}

export class SkillLoadError extends PackError {
  constructor(skillPath: string, cause: Error);
}
```

---

## 5. System Prompt Assembly Rules (v0)

The assembler follows these rules for v0:

### 5.1 Section Order

1. **Identity Section** (first)
   - Agent name and description
   - Operating stance/personality
   - Rules and constraints

2. **Skills Section** (second)
   - Grouped by category
   - Each skill includes name and content
   - Clear separators between skills

3. **Assembly Rules Section** (optional, for debugging)
   - Documents how the prompt was built
   - Lists loaded skills
   - Includes metadata

### 5.2 Content Processing

- **AGENTS.md**: Parsed as-is, preserving markdown formatting
- **SKILL.md**: Loaded as plain text, no execution semantics
- **No template processing**: Skills are instructional text only
- **Size limits**: Individual skills capped at configurable limit (default 100KB)

### 5.3 Default Assembly Configuration

```typescript
const defaultAssemblyRules: AssemblyRules = {
  identityFirst: true,
  includeSkillMetadata: false,  // Keep prompt clean in production
  skillOrdering: 'category',    // Group related skills
  maxPromptLength: 128000,      // Token-aware limit (roughly 32k-128k tokens)
};
```

---

## 6. Test Strategy

### 6.1 Test Structure

```
services/orchestrator/
├── tests/
│   ├── unit/
│   │   └── packs/
│   │       ├── validator.test.ts
│   │       ├── loader.test.ts
│   │       ├── assembler.test.ts
│   │       └── errors.test.ts
│   ├── integration/
│   │   └── packs/
│   │       └── pack-loading.test.ts
│   └── fixtures/
│       └── packs/
│           ├── valid-pack/
│           │   ├── AGENTS.md
│           │   └── .agents/
│           │       └── skills/
│           │           ├── coding/
│           │           │   └── SKILL.md
│           │           └── testing/
│           │               └── SKILL.md
│           ├── missing-agents-md/
│           │   └── .agents/
│           │       └── skills/
│           │           └── empty/
│           │               └── SKILL.md
│           └── large-skills/
│               ├── AGENTS.md
│               └── .agents/
│                   └── skills/
│                       └── huge/
│                           └── SKILL.md   # > max size
```

### 6.2 Unit Tests

**Validator Tests** (`validator.test.ts`):
- Valid pack passes validation
- Missing AGENTS.md fails validation
- Empty pack directory fails validation
- Reports correct error codes

**Loader Tests** (`loader.test.ts`):
- Loads valid pack correctly
- Parses AGENTS.md identity
- Loads all skills from directory
- Handles missing skills directory gracefully
- Respects size limits
- Throws SkillLoadError on read failures

**Assembler Tests** (`assembler.test.ts`):
- Assembles prompt with correct section order
- Groups skills by category
- Respects max prompt length
- Includes identity first when configured
- Formats skills with separators

**Error Tests** (`errors.test.ts`):
- Error types have correct codes
- Error messages are descriptive
- Error chaining preserves cause

### 6.3 Integration Tests

**Pack Loading Flow** (`pack-loading.test.ts`):
- End-to-end: validate → load → assemble
- Real filesystem operations with fixtures
- Performance: large packs load within time limits
- Memory: large skills don't cause OOM

### 6.4 Test Commands

```json
{
  "scripts": {
    "test": "vitest run",
    "test:packs": "vitest run tests/unit/packs",
    "test:packs:watch": "vitest tests/unit/packs",
    "test:integration:packs": "vitest run tests/integration/packs"
  }
}
```

### 6.5 Coverage Targets

- Unit tests: 90% coverage for pack module
- All error paths tested
- All validation rules tested
- Integration: all public API paths covered

---

## 7. Dependencies on Other Sections

### 7.1 Required Before

| Section | Task | Bean | Purpose |
|---------|------|------|---------|
| 1.x | Project Setup | minerva-eegh | TypeScript project structure, dependencies |
| 2.x | Run Model | minerva-d8kv | Run types and service interfaces |

### 7.2 Enables

| Section | Task | Purpose |
|---------|------|---------|
| 5.x | Agent Worker | Provides system prompt to agent loop |
| 6.x | HTTP API | Accepts pack path in run creation |

### 7.3 No Dependencies On

- Daytona sandbox integration (pack loading is filesystem-only)
- SSE streaming (pack loading happens before streaming starts)

---

## 8. Example Usage

### 8.1 Basic Pack Loading

```typescript
import { validatePack, loadPack, assembleSystemPrompt } from '@/packs';

async function createRunWithPack(packPath: string) {
  // 1. Validate
  const validation = await validatePack(packPath);
  if (!validation.valid) {
    throw new Error(`Invalid pack: ${validation.errors.map(e => e.message).join(', ')}`);
  }
  
  // 2. Load
  const pack = await loadPack(packPath);
  
  // 3. Assemble
  const systemPrompt = assembleSystemPrompt(pack);
  
  return {
    pack,
    systemPrompt: systemPrompt.fullPrompt,
    sections: systemPrompt.sections,
  };
}
```

### 8.2 In Run Service

```typescript
// src/services/run-service.ts

export class RunService implements IRunService {
  constructor(
    private packLoader: IPackLoader,
    private promptAssembler: ISystemPromptAssembler,
  ) {}
  
  async createRun(request: CreateRunRequest): Promise<Run> {
    // Validate and load pack
    const pack = await this.packLoader.load(request.packPath);
    
    // Assemble system prompt
    const systemPrompt = this.promptAssembler.assemble(pack);
    
    // Create run with assembled prompt
    const run = await this.runRepo.create({
      ...request,
      systemPrompt: systemPrompt.fullPrompt,
      packMetadata: {
        path: pack.path,
        skillCount: pack.skills.length,
        loadedAt: pack.metadata.loadedAt,
      },
    });
    
    return run;
  }
}
```

---

## 9. Acceptance Criteria

- [ ] `AGENTS.md` is required - packs without it fail validation
- [ ] All `.agents/skills/**/SKILL.md` files are loaded as plain text
- [ ] Skills are instructional-only (no executable code in v0)
- [ ] System prompt combines identity + skills in correct order
- [ ] Validation returns clear error messages for invalid packs
- [ ] Size limits are enforced for individual skills
- [ ] All unit tests pass with 90%+ coverage
- [ ] Integration tests pass with fixture packs
- [ ] Pack loading integrates with RunService
- [ ] Documentation includes example pack structure

---

## 10. Reference Links

### Project Documentation
- [Project Scope](../../../docs/PROJECT.md) - Agent pack concept and structure
- [Coding Standards](../../../docs/CODING_STANDARDS.md) - Quality and architecture rules
- [Architecture Notes](../../../docs/architecture/agent-runtime-v0.md) - Agent pack baseline structure

### Design Documents
- [Proposal](../../../openspec/changes/orchestrator-v0/proposal.md) - Why and what changes (see capabilities section)
- [Design Document](../../../openspec/changes/orchestrator-v0/design.md) - Goals, decisions, risks (see "Skills are instructional-only")
- [Run Model Plan](./run-model-scheduling.md) - Integration point for pack loading

### Related Plans
- [Project Setup](./project-setup.md) - Foundation required before implementation

---

## 11. Notes and Risks

### Risk: Skill Size Limits
Large skill files could cause memory issues or exceed model context windows.

**Mitigation**:
- Configurable size limits (default 100KB per skill)
- Total prompt length tracking
- Warning when approaching limits

### Risk: File System Errors
Permissions issues or missing files during runtime.

**Mitigation**:
- Graceful error handling with descriptive messages
- Validation step to catch issues early
- Clear error codes for debugging

### Risk: Prompt Injection via Skills
Malicious content in SKILL.md could affect agent behavior.

**Mitigation**:
- v0 skills are instructional text only (no code execution)
- Clear documentation that skills don't add capabilities
- Future: content sanitization and policy enforcement

### Risk: Assembly Rule Changes
As prompt engineering evolves, assembly rules may need updates.

**Mitigation**:
- Assembly rules are configurable
- Section ordering is parameterized
- Easy to add new assembly strategies

---

## 12. Future Considerations (Post-v0)

- **Skill Templates**: Support for parameterized skills
- **Skill Dependencies**: Skills that reference other skills
- **Dynamic Loading**: Hot-reload skills without restarting runs
- **Skill Validation**: Verify skill content meets guidelines
- **Pack Versioning**: Version and migrate pack formats
- **External Packs**: Load packs from git repos or URLs

---

*Plan created: 2025-03-09*  
*Status: Ready for implementation*
