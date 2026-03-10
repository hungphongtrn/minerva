# Harvest Loop Boundaries

When verification or fix loops stop being routine, present the user with options instead of deciding autonomously.

## Presentation Rule

- Always stop and wait for the user to choose.
- Present numbered options with a short recommendation, pros, cons, and the reason the workflow is pausing.

## Scenarios

### 1. Simple Bug

- Condition: the failure is isolated, the intended behavior is still clear, and a small fix bean should resolve it.
- Recommended action: create a fix bean and return it to `/harvest-plan`.
- Analysis to present: explain the narrow scope and the expected low-risk correction.
- Rationale: keep momentum without reopening specs.

### 2. Spec Change Needed

- Condition: the implementation matches the current design, but the desired result has changed.
- Recommended action: update OpenSpec first, then create or re-plan follow-up beans.
- Analysis to present: show the mismatch between verified behavior and desired behavior.
- Rationale: avoid hiding a product decision inside a fix loop.

### 3. Scope Creep

- Condition: the requested fix expands beyond the original bean intent.
- Recommended action: split new scope into a separate bean or change.
- Analysis to present: distinguish required repair work from newly discovered expansion.
- Rationale: preserve atomic plans and commits.

### 4. Repeated Failure

- Condition: the same original bean has failed verification more than once.
- Recommended action: escalate to the user with options to continue, redesign, or pause.
- Analysis to present: summarize prior attempts and what each one changed.
- Rationale: prevent infinite loops and churn.

### 5. Deferred Beans

- Condition: a fix is known but should wait for another dependency or decision.
- Recommended action: create a deferred follow-up bean or mark the existing bean blocked.
- Analysis to present: list the blocking dependency and the risk of continuing now.
- Rationale: keep the workflow traceable without forcing premature work.
