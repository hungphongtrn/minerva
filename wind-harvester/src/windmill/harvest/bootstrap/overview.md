# Harvest Bootstrap Overview

Use harvest bootstrap when setting up a project for the first time or when joining an existing repository that has not been wired into OpenSpec and Beans yet.

## When To Use

- Greenfield: the project is new and the team wants starter docs plus initial milestones.
- Brownfield: the codebase exists, but the project docs, OpenSpec, or Beans workflow are missing.
- Re-entry: a contributor needs to verify that the project still has the required docs and tracking scaffolding before starting change work.

## Prerequisites

- The project has a `docs/` folder populated from the bootstrap templates or equivalent docs.
- At minimum, `docs/project/README.md`, `docs/architecture/README.md`, and `docs/roadmap/README.md` exist.
- The roadmap is organized into `## Phase` sections so milestone generation is deterministic.

## Modes

### Greenfield

1. Copy the bootstrap templates into `docs/`.
2. Fill in the templates before running `/harvest-bootstrap`.
3. Let bootstrap initialize OpenSpec, Beans, milestones, and epics.

### Brownfield

1. Reconcile existing docs into the folder-first structure.
2. Preserve existing architecture and roadmap content.
3. Run `/harvest-bootstrap` in idempotent mode so only missing setup is created.

## Bootstrap Sequence

1. Validate the required docs exist and point users to the templates if they do not.
2. Initialize OpenSpec when `openspec/config.yaml` is missing.
3. Initialize Beans when `.beans.yml` is missing.
4. Parse `docs/roadmap/README.md` into milestones and epics.
5. Report what already existed versus what was created.
6. Suggest `/opsx:new` or `/opsx:propose` as the next step.

## Idempotency

- Never overwrite filled docs without an explicit user request.
- Never recreate existing milestones or epics.
- Re-running should only fill missing scaffolding and then exit with a clear status report.
