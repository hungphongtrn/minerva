# DECISIONS

* 2026-03-11T14:27:00+07:00-maintain AGENTS.md Docs TOC and docs/DECISIONS.md as part of documentation changes
- [AGENTS.md](../AGENTS.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/DECISIONS.md](./DECISIONS.md)

* 2026-03-11T14:33:00+07:00-keep AGENTS.md Docs TOC high-level and record every meaningful user decision in docs/DECISIONS.md
- [AGENTS.md](../AGENTS.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-97zj--simplify-agents-docs-toc-and-enforce-user-decision.md](../.beans/minerva-97zj--simplify-agents-docs-toc-and-enforce-user-decision.md)

* 2026-03-11T15:18:00+07:00-remove specification-plugin dependency and standardize on AGENTS.md plus markdown docs and beans
- [AGENTS.md](../AGENTS.md)
- [docs/process/INDEX.md](./process/INDEX.md)
- [docs/process/markdown-beans-workflow.md](./process/markdown-beans-workflow.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/specs/INDEX.md](./specs/INDEX.md)
- [.beans/minerva-0qt4--shift-project-process-from-spec-plugins-to-markdow.md](../.beans/minerva-0qt4--shift-project-process-from-spec-plugins-to-markdow.md)

* 2026-03-11T15:23:00+07:00-create docs/glider as the home for workflow, layered documentation design, and agent planning guidance
- [AGENTS.md](../AGENTS.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/glider/README.md](./glider/INDEX.md)
- [docs/glider/implementation-plan.md](./glider/implementation-plan.md)
- [docs/glider/workflow.md](./glider/workflow.md)
- [docs/glider/layered-documentation-system.md](./glider/layered-documentation-system.md)
- [docs/glider/agent-skills-and-plans.md](./glider/agent-skills-and-plans.md)
- [.beans/minerva-fyzv--plan-glider-documentation-system-and-templates.md](../.beans/minerva-fyzv--plan-glider-documentation-system-and-templates.md)

* 2026-03-11T15:47:00+07:00-move model provider setup and troubleshooting docs into docs/setups and standardize docs indexes on INDEX.md
- [AGENTS.md](../AGENTS.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/setups/INDEX.md](./setups/INDEX.md)
- [docs/setups/model-provider-setup.md](./setups/model-provider-setup.md)
- [docs/setups/model-provider-troubleshooting.md](./setups/model-provider-troubleshooting.md)
- [.beans/minerva-vji0--reorganize-model-provider-docs-into-setups-and-ren.md](../.beans/minerva-vji0--reorganize-model-provider-docs-into-setups-and-ren.md)

* 2026-03-11T15:50:39+07:00-store a reusable project-agnostic AGENTS template in the repository root for reuse across other projects
- [AGENT-TEMPLATE.md](../AGENT-TEMPLATE.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-n8fi--persist-reusable-agents-template.md](../.beans/minerva-n8fi--persist-reusable-agents-template.md)

* 2026-03-11T16:20:00+07:00-use pi coding agent as the session architecture reference while keeping agent behavior unchanged, persisting sessions in Postgres, and continuing tool execution through Daytona sandboxes
- [docs/research/pi-agent-core/sessions.md](./research/pi-agent-core/sessions.md)
- [docs/PROJECT.md](./PROJECT.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T11:11:44+07:00-prefer adapting the pi coding agent SDK behavior rather than relying on pi-agent-core alone, aiming to replicate the reference behavior as closely as practical while substituting Postgres persistence and Daytona sandbox execution
- [docs/research/pi-coding-agent-sdk.md](./research/pi-coding-agent-sdk.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T12:17:15+07:00-target near-exact pi coding agent SDK semantics, keep built-in coding tools and file-based resource loading behavior, preserve branch-capable internals while hiding branching in v1, and run all tool execution inside Daytona with flexible trust restrictions
- [docs/research/pi-coding-agent-sdk.md](./research/pi-coding-agent-sdk.md)
- [docs/specs/sandbox-execution.md](./specs/sandbox-execution.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T12:35:59+07:00-scope v1 around developer-built agents for consumers, using one workspace per user-agent inside a per-user-per-agent Daytona sandbox with inactivity-based disposal, hybrid Postgres persistence that follows pi behavior closely, consumer APIs that block slash commands, pi-like resume semantics without workspace checkpointing, behavioral-plus-export compatibility, and developer extensibility via custom UIs over HTTP/SSE
- [docs/PROJECT.md](./PROJECT.md)
- [docs/research/pi-coding-agent-sdk.md](./research/pi-coding-agent-sdk.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T12:41:51+07:00-follow pi coding agent JSONL durability semantics by persisting durable message/session entries rather than every streaming delta, while keeping live SSE streaming for runtime updates
- [docs/research/pi-coding-agent-sdk.md](./research/pi-coding-agent-sdk.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T12:58:44+07:00-store minerva-qqaa discussion conclusions under docs/disussions and index them as a pre-planning design record linked back to the research and bean
- [docs/disussions/INDEX.md](./disussions/INDEX.md)
- [docs/disussions/minerva-qqaa-pi-coding-agent-alignment.md](./disussions/minerva-qqaa-pi-coding-agent-alignment.md)
- [docs/INDEX.md](./INDEX.md)
- [AGENTS.md](../AGENTS.md)
- [.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md](../.beans/minerva-qqaa--align-orchestrator-session-persistence-with-pi-cod.md)

* 2026-03-12T13:28:00+07:00-establish minerva-qqaa layer-1 design baseline around a hosted session runtime adapter, Postgres-backed append-oriented session persistence, Daytona-backed coding adapters, workspace-materialized runtime resources, and session-aware HTTP/SSE plus pi-shaped export compatibility
- [docs/architecture/minerva-qqaa/INDEX.md](./architecture/minerva-qqaa/INDEX.md)
- [docs/architecture/minerva-qqaa/current-vs-pi-runtime.md](./architecture/minerva-qqaa/current-vs-pi-runtime.md)
- [docs/architecture/minerva-qqaa/session-persistence.md](./architecture/minerva-qqaa/session-persistence.md)
- [docs/architecture/minerva-qqaa/runtime-and-sandbox-adapters.md](./architecture/minerva-qqaa/runtime-and-sandbox-adapters.md)
- [docs/architecture/minerva-qqaa/api-and-export-compatibility.md](./architecture/minerva-qqaa/api-and-export-compatibility.md)
- [docs/architecture/INDEX.md](./architecture/INDEX.md)
- [docs/INDEX.md](./INDEX.md)
- [.beans/minerva-ix5z--produce-layer-1-design-docs-for-minerva-qqaa.md](../.beans/minerva-ix5z--produce-layer-1-design-docs-for-minerva-qqaa.md)

* 2026-03-12T14:26:00+07:00-capture minerva-qqaa layer-2 implementation planning around session-first Postgres repositories, hosted session runtime boundaries, Daytona binding/materialization flow, session-aware HTTP-SSE contracts, pi-shaped export serialization, and phased delivery slices
- [docs/architecture/minerva-qqaa/layer-2-implementation-plan.md](./architecture/minerva-qqaa/layer-2-implementation-plan.md)
- [docs/architecture/minerva-qqaa/INDEX.md](./architecture/minerva-qqaa/INDEX.md)
- [docs/architecture/INDEX.md](./architecture/INDEX.md)
- [docs/INDEX.md](./INDEX.md)
- [.beans/minerva-03i3--produce-layer-2-implementation-planning-for-minerv.md](../.beans/minerva-03i3--produce-layer-2-implementation-planning-for-minerv.md)

* 2026-03-12T16:27:00+07:00-classify documentation by authority level, treating PROJECT, ROADMAP, ARCHITECTURE, API, PROCESS, and ratified SPECS as canonical ground truth; treating research, discussions, and most plans as disposable/supporting artifacts; and grouping coding standards plus commit conventions under shared rulebooks/guidelines docs
- [docs/PROJECT.md](./PROJECT.md)
- [docs/architecture/INDEX.md](./architecture/INDEX.md)
- [docs/process/markdown-beans-workflow.md](./process/markdown-beans-workflow.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-xqzr--define-stable-vs-disposable-documentation-contract.md](../.beans/minerva-xqzr--define-stable-vs-disposable-documentation-contract.md)

* 2026-03-12T16:30:00+07:00-treat beans as both issue tracker and operational memory for stateless agent sessions, requiring bean-creation rules and enough in-bean status/context to recover work from a fresh context
- [docs/process/markdown-beans-workflow.md](./process/markdown-beans-workflow.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-urdx--define-when-beans-should-be-created-as-agent-memor.md](../.beans/minerva-urdx--define-when-beans-should-be-created-as-agent-memor.md)

* 2026-03-12T16:38:00+07:00-codify bean creation thresholds, bean-as-memory recovery requirements, and a standard resumability template in docs/process so fresh agent sessions can recover active work from beans plus linked canonical docs
- [docs/process/bean-memory-policy.md](./process/bean-memory-policy.md)
- [docs/process/bean-template.md](./process/bean-template.md)
- [docs/process/markdown-beans-workflow.md](./process/markdown-beans-workflow.md)
- [docs/process/INDEX.md](./process/INDEX.md)
- [docs/INDEX.md](./INDEX.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-urdx--define-when-beans-should-be-created-as-agent-memor.md](../.beans/minerva-urdx--define-when-beans-should-be-created-as-agent-memor.md)

* 2026-03-12T16:44:00+07:00-group coding standards and commit conventions under docs/rulebooks with a shared rulebook index and update anchor references to the new canonical structure
- [docs/rulebooks/INDEX.md](./rulebooks/INDEX.md)
- [docs/rulebooks/coding-standards.md](./rulebooks/coding-standards.md)
- [docs/rulebooks/commit-guidelines.md](./rulebooks/commit-guidelines.md)
- [docs/INDEX.md](./INDEX.md)
- [AGENTS.md](../AGENTS.md)
- [docs/DECISIONS.md](./DECISIONS.md)
- [.beans/minerva-ki1b--move-standards-docs-into-rulebooks.md](../.beans/minerva-ki1b--move-standards-docs-into-rulebooks.md)
