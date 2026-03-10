# Progressive Disclosure

Progressive disclosure means the agent starts with a small, stable entry point and follows pointers to deeper material only when the task needs it.

## Why It Works

Large instruction files compete with the task, code, and current documentation for limited context window space. When too much generic guidance is loaded up front, the agent has less room for the details that matter right now and is more likely to miss constraints or optimize for the wrong thing.

The goal is not to hide knowledge. The goal is to stage knowledge so the agent reads the right level of detail at the right time.

## Core Principles

### 1. Keep the entry point small

Use `AGENTS.md`, `CLAUDE.md`, or an equivalent root file as a table of contents, not an encyclopedia.

- Keep it short enough to scan quickly.
- Include only instructions that apply to almost every task.
- Link to deeper docs instead of embedding long explanations.

### 2. Put detail in focused documents

Store domain knowledge in topic-specific files under `docs/`.

- Split by concern such as architecture, product specs, security, or plans.
- Keep each document focused on one topic.
- Prefer an index file for each subdirectory.

### 3. Teach navigation, not memorization

The entry point should tell the agent where to look next.

- Point to the best starting docs for common tasks.
- Cross-link related documents.
- Make filenames descriptive so search and retrieval are easy.

### 4. Keep universal rules separate from task-specific rules

Universal rules belong in the root instruction file. Task-specific, team-specific, or domain-specific guidance belongs in referenced docs.

- Put coding style in linters and formatters when possible.
- Put implementation details in focused design or spec docs.
- Avoid pasting one-off instructions into the global entry point.

### 5. Optimize for retrieval

Good progressive disclosure assumes the agent can fetch more context as needed.

- Use predictable directories.
- Use README indexes in subdirectories.
- Avoid giant mixed-purpose files that are hard to search.

## Mechanical Rule of Thumb

Every token that is not helping with the current task is competing with something more relevant.

Use this rule when deciding where information belongs:

- If it applies to nearly all tasks, keep it in the entry point.
- If it applies to a category of work, put it in a focused indexed doc.
- If it applies only to one change or feature, keep it in a plan, spec, or change-specific document.

## Recommended Structure

```text
AGENTS.md or CLAUDE.md    <- short entry point with pointers
docs/
  README.md               <- top-level documentation index
  architecture/
    README.md
    runtime.md
    state-machines.md
  product-specs/
    README.md
    onboarding.md
  security/
    README.md
    auth-model.md
  plans/
    README.md
    feature-x.md
```

## Authoring Checklist

Use this checklist when maintaining an agent-facing entry point:

- Keep it short and stable.
- Keep only universally applicable instructions inline.
- Replace long explanations with links to focused docs.
- Add or update index files when new docs are created.
- Cross-link related material so the next hop is obvious.
- Move code style rules into tooling where possible.

## Example Application

Instead of writing one comprehensive `AGENTS.md`, use:

- a concise root file that explains core rules and links to docs
- a `docs/` tree with focused sections such as design docs, execution plans, product specs, references, and security
- small indexes that help the agent load the right document for the current task

This gives the agent a narrow default context and a clear retrieval path to deeper guidance.

## Anti-Patterns

Avoid these common failures:

- a root file that tries to document the whole system
- repeated instructions copied across many files
- mixed-purpose documents that combine architecture, plans, specs, and workflow rules
- task-specific details embedded in the global entry point

## Bottom Line

Progressive disclosure is a context management strategy. Start small, point clearly, and let the agent pull in deeper material only when the task requires it.
