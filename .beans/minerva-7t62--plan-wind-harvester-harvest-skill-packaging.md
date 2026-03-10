---
# minerva-7t62
title: Plan wind-harvester harvest skill packaging
status: completed
type: task
priority: normal
created_at: 2026-03-09T18:00:50Z
updated_at: 2026-03-09T18:01:22Z
---

Create an implementation plan for reorganizing harvest-related commands and skills with progressive disclosure and a packaged wind-harvester folder.

## Todo
- [ ] Review current harvest commands, skills, and related docs
- [ ] Identify how progressive disclosure should split shared vs command-specific content
- [x] Draft a concrete folder/package migration plan for wind-harvester/src and windmill shared assets

## Summary of Changes

Reviewed the current harvest command and skill layout, the harvest workflow docs, and the project progressive disclosure guidance. Drafted a staged migration plan for packaging harvest assets into `wind-harvester/src/` with a shared `windmill/` folder for common references and deeper materials.
