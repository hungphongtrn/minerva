---
phase: quick-006-explore-zeroclaw-reference-and-create-a
plan: 006
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py
  - .planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md
autonomous: true
must_haves:
  truths:
    - "A standalone toy script can create one Daytona sandbox, start Zeroclaw gateway, and successfully call POST /webhook with a bearer token."
    - "The toy script supports a dry-run mode that validates local prerequisites without needing Daytona credentials."
    - "Findings are documented in markdown (what is referenced, what the toy demonstrates, how to run, what to expect) without modifying repo src/."
  artifacts:
    - path: ".planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py"
      provides: "Raw Daytona Async SDK toy: provision sandbox + start gateway + call /health and /webhook"
      contains: "AsyncDaytona"
    - path: ".planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md"
      provides: "Repository-backed notes and runbook for the toy"
      contains: "How to run"
  key_links:
    - from: ".planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py"
      to: "src/integrations/zeroclaw/spec.json"
      via: "loads gateway port/paths/start_command"
      pattern: "spec\\.json"
    - from: ".planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py"
      to: "sandbox.fs.upload_file"
      via: "writes /workspace/.zeroclaw/config.json"
      pattern: "upload_file"
    - from: ".planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py"
      to: "gateway /webhook"
      via: "httpx POST with Authorization: Bearer"
      pattern: "Authorization"
---

<objective>
Explore in-repo Zeroclaw/Daytona gateway reference and produce a standalone `pseudo_toy.py` (raw Daytona Async SDK) that provisions one gateway-mode sandbox, starts Zeroclaw gateway, and demonstrates webhook chat interactions; capture the findings as markdown.

Purpose: create a minimal, runnable mental model of the Daytona Async SDK + Zeroclaw gateway contract (health + webhook) without changing production code.
Output: `.planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py` and `.planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md`.
</objective>

<execution_context>
./.opencode/get-shit-done/workflows/execute-plan.md
./.opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md

# In-repo references (read-only)
@src/integrations/zeroclaw/spec.json
@src/infrastructure/sandbox/providers/daytona.py
@src/services/zeroclaw_gateway_service.py
@.planning/quick/3-replace-execute-with-webhook-and-evaluat/3-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create pseudo_toy.py (raw AsyncDaytona) to provision sandbox, start gateway, and call /webhook</name>
  <files>.planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py</files>
  <action>
Create `.planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py` as a standalone async script (toy/experiment, not production) that uses the Daytona Async SDK directly (import from `daytona`, not from Minerva provider services).

Hard constraints:
- Do NOT modify anything under repo root `src/` (this quick task is read-only with respect to product code).
- Follow the repo invariant: run python via `uv run ...`.
- Keep file ASCII-only.
- No new dependencies; use `daytona` + `httpx` already in `pyproject.toml`.

Behavior (must be implemented exactly; use flags to avoid needing credentials in automated verification):
- `--dry-run` (default):
  - Load and parse `src/integrations/zeroclaw/spec.json`.
  - Print (stdout) the derived defaults it would use: snapshot name, target region, gateway port, health path, execute path, start command, config path.
  - Print the required env vars for live mode: `DAYTONA_API_KEY` (or `DAYTONA_API_TOKEN`), optional `DAYTONA_API_URL`, optional `DAYTONA_TARGET`.
  - Exit 0 without calling Daytona.

- `--run` (live):
  1) Build `DaytonaConfig` from env vars (prefer `DAYTONA_API_KEY`, fallback to `DAYTONA_API_TOKEN`; default region from `spec.daytona.target_region` unless overridden by `DAYTONA_TARGET`).
  2) Create a sandbox using `CreateSandboxFromSnapshotParams(snapshot=spec.daytona.snapshot_name, timeout=60, labels=..., env_vars=..., volumes=None)`.
     - Labels: include at least `minerva.quick_task=6` and `zeroclaw.version={spec.version}`.
     - env_vars: forward any present `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` so the runtime can run if needed.
  3) Resolve the gateway URL using the sandbox instance methods (same strategy as `src/infrastructure/sandbox/providers/daytona.py`):
     - Try `get_preview_link`, `create_preview_link`, `create_signed_preview_url` for port `spec.gateway.port`.
     - Fallback to `sandbox.preview_url` / `sandbox.url`.
  4) Generate a random bearer token (e.g., `secrets.token_urlsafe(24)`), and write a Zeroclaw `config.json` to `spec.runtime.config_path` via `sandbox.fs.create_folder` + `sandbox.fs.upload_file`.
     - Config JSON shape should match the provider-generated shape in `src/infrastructure/sandbox/providers/daytona.py` `_generate_zeroclaw_config()`.
     - Token must be stored at `config["auth"]["token"]`.
  5) Start the gateway runtime by running `spec.runtime.start_command` via `sandbox.process.exec(...)`.
  6) Poll the gateway for readiness by calling `GET {gateway_url}{spec.gateway.health_path}` with `Authorization: Bearer {token}` until it succeeds (bounded timeout; show progress).
  7) Demonstrate webhook chat interactions by sending 2 sequential `POST {gateway_url}{spec.gateway.execute_path}` requests with the same `context.session_id` and `context.sender_id`:
     - Request body must match the Zeroclaw examples from `spec.json`: `{ "message": "...", "context": {"session_id": "...", "sender_id": "..."} }`.
     - Print response status + response JSON (or text) for each call.
  8) Provide `--cleanup` flag to stop/delete the sandbox at the end (best-effort; failures should be logged but not crash cleanup).

Notes:
- Keep the script readable; include small helper functions: `load_spec()`, `maybe_await()`, `resolve_gateway_url()`, `write_zeroclaw_config()`, `poll_health()`, `post_webhook()`.
- The goal is not perfect parity with Minerva provisioning; it is a minimal, raw-SDK, end-to-end demonstration of: provision -> start -> health -> webhook.
  </action>
  <verify>uv run python .planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py --dry-run</verify>
  <done>
`pseudo_toy.py` exists, runs in `--dry-run` mode without credentials, and contains a `--run` mode that (when configured) provisions one sandbox and calls `GET /health` then `POST /webhook` with bearer auth.
  </done>
</task>

<task type="auto">
  <name>Task 2: Write markdown findings/runbook grounded in repo references (no src changes)</name>
  <files>.planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md</files>
  <action>
Create `.planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md` documenting what was learned and how the toy maps onto in-repo reference.

Required sections (use these headings verbatim):
- `## What I Referenced (In-Repo)`
  - Link the exact files and what each contributed: `src/integrations/zeroclaw/spec.json`, `src/infrastructure/sandbox/providers/daytona.py` (provision + fs upload + start), `src/services/zeroclaw_gateway_service.py` (request shape, /webhook), and `.planning/quick/3-replace-execute-with-webhook-and-evaluat/3-SUMMARY.md` (webhook-first decision).

- `## Toy Scope` (what it does / what it intentionally does not do)

- `## How to Run`
  - Dry-run command.
  - Live-run command with required env vars.
  - Optional cleanup usage.

- `## Webhook Contract (Request/Response)`
  - Show the exact JSON payload used (from spec examples) and mention bearer header.

- `## Troubleshooting Checklist`
  - Auth failures (token mismatch), gateway not listening, preview URL missing, snapshot missing, 401 on /health.

Constraints:
- Keep it concise and actionable (runbook style).
- Do not add or modify any files under `src/`.
  </action>
  <verify>uv run python -c "from pathlib import Path; p=Path('.planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-FINDINGS.md'); s=p.read_text(encoding='utf-8'); assert '## How to Run' in s and '## Troubleshooting Checklist' in s and 'src/integrations/zeroclaw/spec.json' in s"</verify>
  <done>
Findings doc exists and provides a copy-pastable runbook + clear mapping to the repo reference implementation.
  </done>
</task>

</tasks>

<verification>
- Script dry-run: `uv run python .planning/quick/6-explore-zeroclaw-reference-and-create-a-/pseudo_toy.py --dry-run`
- Findings structure: `uv run python -c "...assert headings..."`
</verification>

<success_criteria>
- A single-file toy demonstrates (when configured) the end-to-end flow: provision sandbox -> write config.json -> start gateway -> bearer-auth health -> bearer-auth webhook.
- Documentation is enough for a teammate to reproduce the toy without reading `src/` code.
</success_criteria>

<output>
After completion, create `.planning/quick/6-explore-zeroclaw-reference-and-create-a-/6-SUMMARY.md`
</output>
