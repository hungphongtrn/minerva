---
# minerva-jrub
title: Reclassify unapproved minerva-qqaa architecture docs as plan artifacts
status: completed
type: task
priority: normal
created_at: 2026-03-14T12:14:51Z
updated_at: 2026-03-14T12:19:21Z
parent: minerva-qqaa
---

Parent feature: minerva-qqaa

## Objective
Move the remaining unapproved proposal content under docs/architecture/minerva-qqaa into docs/plans/minerva-qqaa, keep architecture docs as stable ground truth only, and update AGENTS.md with a clearer canonical vs disposable definition.

## Tasks
- [x] Audit current docs/architecture/minerva-qqaa and determine what remains proposal/planning content
- [x] Move or rewrite unapproved material under docs/plans/minerva-qqaa and refresh indexes/references
- [x] Update AGENTS.md with canonical vs disposable definitions and log the user decision in docs/DECISIONS.md
- [x] Add a summary of changes when complete

## Summary of Changes
- Moved the remaining unapproved minerva-qqaa proposal docs from docs/architecture/minerva-qqaa/ into docs/plans/minerva-qqaa/.
- Rewrote docs/architecture/minerva-qqaa/INDEX.md into a canonical status note that keeps minerva-qqaa out of canonical architecture until approval.
- Updated AGENTS.md and docs/process/markdown-beans-workflow.md to define canonical vs disposable docs and to keep canonical ground truth stable until plans are finalized and approved.
- Refreshed docs indexes and docs/DECISIONS.md to classify the moved material as disposable/supporting plan artifacts.
