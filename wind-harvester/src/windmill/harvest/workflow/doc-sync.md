# Living Doc Sync

Run a doc drift review after all beans for a change verify and before suggesting `/opsx-archive`.

## When To Run

- After `/harvest-check` confirms all relevant beans are verified.
- Before the final archive suggestion.

## Drift Categories

- Addition: the implementation introduced new behavior that should be documented.
- Contradiction: the docs say something the implementation no longer does.
- Deprecation: a prior path still exists in docs but should now be retired.
- Growth: a doc has become too large and should be decomposed while syncing changes.

## Action Pattern

1. Present the drift findings.
2. Group findings by doc path.
3. Ask the user which updates to make now.
4. Commit accepted doc updates with `docs(<scope>): sync <doc> with <change> implementation`.

## Rule

- The agent identifies drift, but the user decides which documentation updates to apply before archive.
