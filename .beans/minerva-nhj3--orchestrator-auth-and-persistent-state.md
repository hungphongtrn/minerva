---
# minerva-nhj3
title: 'Orchestrator: auth and persistent state'
status: scrapped
type: epic
priority: high
created_at: 2026-03-10T09:01:46Z
updated_at: 2026-03-11T06:50:21Z
---

## Goal\n\nHarden the orchestrator for real usage by enforcing API authentication and replacing in-memory run and stream state with persistent/shared storage.\n\n## Outcomes\n\n- API auth is enforced consistently across run and stream endpoints\n- Run metadata and event history survive process restarts\n- The service can evolve toward multi-instance deployment without losing correctness\n\n## Child Work Ideas\n\n- [x] Implement API key auth guards or equivalent request authentication\n- [ ] Persist runs, leases, and related state in a database-backed store\n- [ ] Persist or replay SSE event history from durable/shared storage\n- [ ] Align API/auth docs with shipped behavior
