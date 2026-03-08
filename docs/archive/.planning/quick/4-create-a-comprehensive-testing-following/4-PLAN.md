---
phase: quick-4-create-a-comprehensive-testing-following
plan: 4
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md
autonomous: true
requirements: ["QUICK-4"]

must_haves:
  truths:
    - "All test/workflow commands from DEV-WORKFLOW.md are executed OR explicitly skipped with a recorded reason"
    - "Every failure is documented with exact repro command(s), exit code, and the most relevant error excerpt"
    - "No source-code fixes are applied (only observation + documentation)"
  artifacts:
    - path: ".planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md"
      provides: "Single consolidated testing report + issues log"
  key_links:
    - from: "DEV-WORKFLOW.md"
      to: ".planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md"
      via: "Section-by-section command execution + results"
      pattern: "DEV-WORKFLOW"
---

<objective>
Run a comprehensive, read-only verification pass following `DEV-WORKFLOW.md`, and document every issue found (docs gaps, command failures, mismatches, unclear requirements) without fixing anything.

Purpose: Establish an evidence-backed baseline of current dev workflow reliability.
Output: A single report file capturing commands run, results, and an actionable issue list.
</objective>

<context>
@DEV-WORKFLOW.md
@pyproject.toml
@docker-compose.yml
@src/config/settings.py
@src/cli/commands/serve.py
@src/cli/commands/init.py
</context>

<tasks>

<task type="auto">
  <name>Run baseline test suite + non-mutating workflow checks</name>
  <files>.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md</files>
  <action>
Create `.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md` with these sections (exact headings):

- `## Scope` (explicitly state: observation only; no fixes; no commits)
- `## Environment` (record: OS, `uv --version`, `uv run python -V`)
- `## Baseline Commands` (each command with: purpose, exact command line, exit code, and 10-40 lines of relevant output)

Then run and record:

1) Dependency install / lock health
   - `uv sync --dev`

2) Import/syntax smoke
   - `uv run python -m compileall src`

3) Unit/integration tests
   - `uv run pytest`

4) DEV-WORKFLOW init behavior WITHOUT mutating tracked files
   - Do NOT run `uv run minerva init` (it regenerates `.env.example`).
   - Instead, compare current `.env.example` to the init template output and record whether they match:
     - `uv run python -c "from pathlib import Path; from src.cli.commands.init import _render_env_example_template as r; cur=Path('.env.example').read_text(encoding='utf-8'); gen=r(); print('env_example_matches_template=', cur==gen); print('current_len=',len(cur)); print('generated_len=',len(gen))"`

In the report, add a small `## Notes` subsection capturing any doc mismatches discovered during this task (example targets: Python version requirement mismatch, default sandbox profile mismatch).
  </action>
  <verify>
    <automated>uv run python -c "from pathlib import Path; p=Path('.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md'); s=p.read_text(encoding='utf-8'); assert '## Baseline Commands' in s; assert 'uv sync --dev' in s; assert 'uv run pytest' in s; assert 'compileall' in s"</automated>
  </verify>
  <done>
`.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md` exists and includes recorded results (including exit codes) for `uv sync --dev`, `uv run python -m compileall src`, `uv run pytest`, and the `.env.example` vs template comparison.
  </done>
</task>

<task type="auto">
  <name>Exercise DEV-WORKFLOW local stack (docker + migrate) and minimal server health check</name>
  <files>.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md</files>
  <action>
Extend `.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md` with a new section: `## DEV-WORKFLOW Smoke Pass`.

Follow the DEV-WORKFLOW intent (local dependencies + DB setup), but keep the repo read-only:

1) Validate compose file parses
   - `docker compose config`

2) Start dependencies (Postgres + MinIO)
   - `docker compose up -d postgres minio`
   - `docker compose ps`

3) Run migrations against the compose Postgres (do NOT create/edit `.env`)
   - Use the connection string implied by `docker-compose.yml` defaults:
     - `DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw uv run minerva migrate`

4) Start server briefly and hit `/health` (skip preflight so this remains an execution smoke test, not a full environment setup)
   - `DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw SANDBOX_PROFILE=local_compose uv run minerva serve --skip-preflight --host 127.0.0.1 --port 8001 & SERVER_PID=$!; sleep 2; curl -fsS http://127.0.0.1:8001/health; STATUS=$?; kill $SERVER_PID; exit $STATUS`

5) Tear down dependencies (so the run is self-contained)
   - `docker compose down`

For each command: capture exit code + key output in the report. If any step fails, document:
- Exact error excerpt
- What DEV-WORKFLOW.md suggests should happen
- What actually happened
- Any suspected missing prerequisites/variables
  </action>
  <verify>
    <automated>uv run python -c "from pathlib import Path; s=Path('.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md').read_text(encoding='utf-8'); assert '## DEV-WORKFLOW Smoke Pass' in s; assert 'docker compose up -d postgres minio' in s; assert 'uv run minerva migrate' in s; assert '/health' in s"</automated>
  </verify>
  <done>
Report contains a DEV-WORKFLOW smoke section with docker compose validation, dependency startup, migration attempt, a `/health` request attempt, and teardown results.
  </done>
</task>

<task type="auto">
  <name>Write issues-only log (no fixes) with repro steps and evidence</name>
  <files>.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md</files>
  <action>
Finalize `.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md` by adding these sections:

- `## Issues` (bulleted list; each issue includes: Severity {blocking|major|minor|nit}, Where (file/command), Repro command(s), Expected, Actual, Evidence snippet)
- `## Git Workspace After Running` (paste `git status --porcelain` output; if any untracked artifacts are created by running commands, list them and keep them uncommitted)
- `## What Was Not Tested` (only items that require external credentials or long-running operations; include the reason and the doc section that mentioned it)

Hard rule: Do NOT change any production code/config as part of this task; only write the report.
  </action>
  <verify>
    <automated>uv run python -c "from pathlib import Path; s=Path('.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md').read_text(encoding='utf-8'); assert '## Issues' in s; assert '## Git Workspace After Running' in s; assert '## What Was Not Tested' in s"</automated>
  </verify>
  <done>
Report contains a clearly separated issues list with repro steps and includes post-run `git status --porcelain` evidence.
  </done>
</task>

</tasks>

<success_criteria>
- `.planning/quick/4-create-a-comprehensive-testing-following/4-TESTING-REPORT.md` exists and is sufficient for someone else to reproduce every reported failure.
- No code fixes or refactors were applied; only commands were executed and results documented.
</success_criteria>
