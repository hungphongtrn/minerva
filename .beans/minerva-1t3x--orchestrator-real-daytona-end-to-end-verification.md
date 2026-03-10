---
# minerva-1t3x
title: 'Orchestrator: real Daytona end-to-end verification'
status: todo
type: epic
priority: normal
created_at: 2026-03-10T09:01:46Z
updated_at: 2026-03-10T09:01:46Z
---

## Goal\n\nProve the orchestrator works against a real Daytona environment and a real sample pack, not only mocks, before calling it ready for broader use.\n\n## Outcomes\n\n- A reproducible end-to-end validation path exists for real sandbox execution\n- A sample pack can be run through the public API and SSE stream\n- Remaining Daytona integration gaps are documented and tracked\n\n## Child Work Ideas\n\n- [ ] Add a committed sample pack or documented fixture for live verification\n- [ ] Run end-to-end API plus SSE tests against a real Daytona server\n- [ ] Validate sandbox lifecycle, file operations, and bash execution in practice\n- [ ] Capture follow-up bugs or hardening work from real-environment findings
