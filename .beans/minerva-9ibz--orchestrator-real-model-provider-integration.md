---
# minerva-9ibz
title: 'Orchestrator: real model provider integration'
status: completed
type: epic
priority: high
created_at: 2026-03-10T09:01:46Z
updated_at: 2026-03-10T15:52:44Z
---

## Goal\n\nReplace the scripted runtime with a real LLM provider integration so the orchestrator can execute actual agent runs instead of demo-only scripted behavior.\n\n## Outcomes\n\n- Runtime uses a configurable real model provider instead of the scripted stream\n- Secrets/config for model access are validated and documented\n- Run execution, streaming, cancellation, and tool usage work against a real model backend\n\n## Child Work Ideas\n\n- [ ] Add provider abstraction and configuration for real model backends\n- [ ] Replace scripted model wiring in the runtime path\n- [ ] Add integration coverage for real model execution behavior\n- [ ] Update docs and sample environment configuration



## OpenSpec Change

Change directory: openspec/changes/minerva-9ibz/

### Artifacts Created

- **proposal.md**: Problem statement, what changes, new/modified capabilities (model-provider, run-orchestration), and impact assessment
- **design.md**: Technical design with context, goals/non-goals, key decisions (pi-agent-core integration, NestJS DI, environment config), risks and trade-offs
- **specs/model-provider/spec.md**: New capability specification for provider abstraction, configuration validation, health checks, model selection
- **specs/run-orchestration/spec.md**: Delta spec modifying run-orchestration to use real LLM instead of scripted runtime
- **tasks.md**: 32 implementation tasks organized into 7 groups (config, provider service, health checks, orchestration updates, testing, docs, cleanup)
