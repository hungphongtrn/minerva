# Granular Commit Guidelines

This document outlines our commit conventions. We use [Conventional Commits](https://www.conventionalcommits.org/) but enforce stricter granularity and context requirements to ensure long-term traceability, easier debugging (`git bisect`), and safer reverts.

## 1. Principles

1. **Atomic Commits**: Each commit should do exactly one thing. Do not mix refactoring with new features or bug fixes in the same commit.
2. **Traceable Context**: Every commit must provide enough context to understand *why* a change was made without needing to consult an external system.
3. **Bean Integration**: Every commit must reference the relevant Bean (Issue Trackers).

## 2. Commit Message Structure

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### 2.1 Types

We use standard conventional commit types, but limit them to enforce clarity:

- `feat`: A new feature or capability.
- `fix`: A bug fix.
- `refactor`: A code change that neither fixes a bug nor adds a feature (e.g., renaming variables, extracting functions).
- `perf`: A code change that improves performance.
- `test`: Adding missing tests or correcting existing tests.
- `docs`: Documentation only changes.
- `chore`: Maintenance tasks, dependency updates, build process changes.
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc).

### 2.2 Scope

The `<scope>` must uniquely identify the business domain or architectural layer being modified (e.g., `agent-runtime`, `docs`, `harvest`, `ui`, `provider`).

If a change affects multiple scopes, it likely indicates the commit is NOT atomic and should be broken down. If it must be a single commit, use a comma-separated list or omit the scope and explain in the body.

### 2.3 Subject

- Use the imperative, present tense: "change" not "changed" nor "changes".
- Do not capitalize the first letter.
- No dot (.) at the end.
- Must be <= 50 characters.

**Good:** `feat(harvest): add smart-planner event handling`
**Bad:** `added event handling for planner workflow`

### 2.4 Body

The body is mandatory for all commits except trivial `chore`, `style`, or `docs`.

- Explain **WHAT** changed and **WHY** it changed. (The *how* is usually obvious from the diff).
- If replacing an existing piece of logic, explain why the previous logic was flawed.
- Wrap lines at 72 characters.
- Use bullet points for multiple granular points inside the same atomic change.

### 2.5 Footer

The footer is used for referencing issues (Beans) and noting breaking changes.

- **Breaking Changes:** Must start with `BREAKING CHANGE:` followed by a space or two newlines. The rest of the commit message is then used for this.
- **References:** Always reference the Bean ID (e.g., `Refs: Bean-123` or `Fixes: Bean-456`).

## 3. Granularity Rules

To maintain high traceability, follow these specific granularity constraints:

### Rule 1: Isolate Refactoring from Logic Changes

If you need to change existing code to add a new feature, do it in two commits:
1. `refactor(scope): extract function X to prepare for Y`
2. `feat(scope): implement feature Y using X`

### Rule 2: Separate Code from Configuration

Changes to environment variables, YAML configs, or deployment manifests must be separated from application code changes.
1. `chore(config): add API_URL to runtime environment`
2. `feat(api): connect to API_URL for data fetching`

### Rule 3: Single Layer Focus

Avoid changes across the entire architectural stack (`Types -> Config -> Repo -> Service -> Runtime -> UI`) in one commit. Progress sequentially:
1. `feat(types): define UserProfile schema`
2. `feat(repo): implement UserProfile db adapter`
3. `feat(ui): add UserProfile page component`

### Rule 4: Granular Bug Fixes

A fix commit should contain the minimal code necessary to resolve the bug, plus the test that verifies the fix.

## 4. Examples

**Ideal Feature Commit:**

```text
feat(harvest): implement smart-coder verification step

Introduces the check phase in the harvest workflow to validate
code changes automatically. This relies on the pi-agent-core event
bus to stream intermediate thoughts before yielding the final validation
status.

Refs: Bean-42
```

**Ideal Refactor Commit:**

```text
refactor(agent-runtime): extract execution loop state machine

Moves the monolithic execution loop from `runtime.ts` into a dedicated
state machine class to make it easier to test individual state transitions
and prepare for the upcoming pause/resume capability.

Refs: Bean-88
```

**Ideal Fix Commit:**

```text
fix(ui): prevent infinite re-render in project dashboard

The useEffect hook was missing the project ID in its dependency array,
causing continuous re-fetching whenever the component updated. Now it
explicitly tracks project ID mutations.

Fixes: Bean-101
```
