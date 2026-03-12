---
# minerva-urdx
title: Define when beans should be created as agent memory records
status: completed
type: task
priority: normal
created_at: 2026-03-12T15:29:11Z
updated_at: 2026-03-12T15:36:56Z
---

Define bean creation rules so beans act as both issue tracker and operational memory for stateless coding-agent sessions.

## Goals
- [x] Define triggers for creating a new bean versus reusing an existing bean
- [x] Define the minimum status/context each active bean should carry for fresh-session recovery
- [x] Propose a practical bean-as-memory policy for discussion with the user

## Summary of Changes
Added docs/process/bean-memory-policy.md to define bean-creation thresholds, reuse rules, recovery expectations, and session start/end habits. Added docs/process/bean-template.md as the standard resumable bean body structure. Updated docs/process/markdown-beans-workflow.md, docs/process/INDEX.md, docs/INDEX.md, and docs/DECISIONS.md so the process now treats beans as the operational memory layer for stateless agent sessions.
