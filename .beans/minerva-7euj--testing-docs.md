---
# minerva-7euj
title: Testing + Docs
status: todo
type: task
priority: low
tags:
    - harvest
    - orchestrator-v0
created_at: 2026-03-09T08:10:51Z
updated_at: 2026-03-09T08:31:28Z
parent: minerva-5rrj
blocked_by:
    - minerva-goow
---

## Requirements

- [ ] 7.1 Add unit tests for queue/lease behavior (single active run per user)
- [ ] 7.2 Add unit tests for SSE sequencing (`seq` monotonicity) and termination at run completion
- [ ] 7.3 Add integration test (or harness) that runs a simple `bash` command in Daytona and streams output
- [ ] 7.4 Update docs to reflect implemented API endpoints and event schema

## References

- **Proposal**: openspec/changes/orchestrator-v0/proposal.md
- **Design**: openspec/changes/orchestrator-v0/design.md
- **Tasks**: openspec/changes/orchestrator-v0/tasks.md



## Plan

See detailed implementation plan: [docs/plans/orchestrator-v0/testing-docs.md](../../../docs/plans/orchestrator-v0/testing-docs.md)
