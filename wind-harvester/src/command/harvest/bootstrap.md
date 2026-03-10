---
description: Initialize project docs, OpenSpec, Beans, and roadmap milestones for harvest workflows
---

Bootstrap a repository for harvest work.

> **Workflow**: see `{{WINDMILL_ROOT}}/workflow/overview.md`
> **Bootstrap overview**: see `{{WINDMILL_ROOT}}/bootstrap/overview.md`
> **Doc templates**: see `{{WINDMILL_ROOT}}/bootstrap/doc-templates.md`
> **Milestone creation**: see `{{WINDMILL_ROOT}}/bootstrap/milestone-creation.md`
> **Skill entry point**: see `{{SKILL_ROOT}}/harvest-bootstrap/SKILL.md`

---

**Steps**

1. Check whether the required docs exist, with a minimum of `docs/project/README.md`, `docs/architecture/README.md`, and `docs/roadmap/README.md`.
2. If the docs folder is missing or incomplete, copy the bootstrap templates into `docs/` without overwriting filled files.
3. Initialize OpenSpec when `openspec/config.yaml` does not exist.
4. Initialize Beans when `.beans.yml` does not exist.
5. Parse `docs/roadmap/README.md` into ordered milestones and epic beans.
6. Skip milestone or epic creation when matching items already exist.

**Guardrails**

- Keep the command idempotent.
- Do not overwrite user-authored docs.
- Stop early if the roadmap lacks `## Phase` sections.

**Hint Block**

- `✅ Done`: report which docs, tools, milestones, and epics were created versus reused.
- `🔜 Next Steps`: suggest `/opsx:new` or `/opsx:propose` for the first planned change.
- `📎 Context Files`: include the roadmap path and any created doc paths.
