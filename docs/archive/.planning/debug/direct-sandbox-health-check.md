---
status: resolved
trigger: "Investigate specific sandbox (a5dc49e2-2bc9-4d62-b5ce-884f29ccc719) DIRECTLY via Daytona SDK to isolate where failures occur."
created: 2026-03-03T16:50:46Z
updated: 2026-03-03T16:58:07Z
---

## Current Focus
hypothesis: Confirmed - sandbox exists in Daytona but Picoclaw runtime bootstrap never completed, so no reachable bridge path is available.
test: Correlate DB record absence + Daytona STARTED state + missing in-sandbox runtime process/port.
expecting: Combined evidence isolates failure to orchestrator state/hydration lifecycle, not Daytona control plane.
next_action: Report root cause and operational remediation steps.

## Symptoms
expected: Sandbox reported as Started should be reachable by Daytona SDK, gateway health, bridge endpoint, and direct process execution.
actual: User reports sandbox state as Started but failures occur in flow and failure layer is unknown.
errors: Not yet captured; need direct command output from DB, SDK, gateway, bridge, and process execution checks.
reproduction: Investigate the specific sandbox id `a5dc49e2-2bc9-4d62-b5ce-884f29ccc719` with steps 1-5 sequentially.
started: Unknown from report.

## Eliminated

## Evidence

- timestamp: 2026-03-03T16:51:11Z
  checked: Step 1 DB lookup script via `uv run python`
  found: `ModuleNotFoundError: No module named 'src.db.database'`
  implication: Investigation blocked by import path mismatch; need correct DB module before querying state.

- timestamp: 2026-03-03T16:51:33Z
  checked: Source layout for database session initialization
  found: DB engine is defined in `src/db/session.py` as sync `get_engine()`; no `src.db.database` module exists.
  implication: Need to run DB checks using sync SQLAlchemy session/connection APIs.

- timestamp: 2026-03-03T16:51:51Z
  checked: `sandbox_instances` query for id/provider_ref `a5dc49e2-2bc9-4d62-b5ce-884f29ccc719`
  found: Query executed successfully against Postgres but returned no rows (`Sandbox not found in database!`).
  implication: Local orchestrator state lacks this sandbox mapping; next check is whether Daytona still has the workspace.

- timestamp: 2026-03-03T16:52:34Z
  checked: Step 2 script using `from daytona_sdk import Daytona`
  found: `ModuleNotFoundError: No module named 'daytona_sdk'`
  implication: SDK usage in instructions mismatches installed package; must use `daytona` module (`AsyncDaytona`) for direct checks.

- timestamp: 2026-03-03T16:53:20Z
  checked: Step 2 via `AsyncDaytona().get('a5dc49e2-2bc9-4d62-b5ce-884f29ccc719')`
  found: Workspace exists in Daytona with `state=SandboxState.STARTED`, `target=eu`, and matching id/name.
  implication: Daytona control plane connectivity/auth is working; mismatch is between Daytona reality and local DB record.

- timestamp: 2026-03-03T16:53:50Z
  checked: Step 3 gateway resolution + `/health` probe
  found: Provider resolved `https://gateway-a5dc49e2-2bc9-4d62-b5ce-884f29ccc719.us.daytona.run:18790`; probe failed with `ConnectError: [Errno 8] nodename nor servname provided, or not known`.
  implication: Gateway URL is currently non-resolvable; region mismatch is a strong candidate because Daytona reports sandbox target `eu`.

- timestamp: 2026-03-03T16:54:12Z
  checked: Direct probes against both `gateway-...us.daytona.run` and `gateway-...eu.daytona.run`
  found: Both endpoints fail DNS resolution with identical `ConnectError [Errno 8] nodename nor servname provided`.
  implication: Failure is likely URL pattern/endpoint strategy drift rather than only wrong region.

- timestamp: 2026-03-03T16:54:55Z
  checked: Daytona sandbox metadata and available SDK methods
  found: Sandbox `public=False` with no URL fields; SDK provides `get_preview_link(port)` and `create_signed_preview_url(port, ...)` methods.
  implication: Runtime ingress likely requires preview-link APIs, not hardcoded `gateway-<id>...` hostname construction.

- timestamp: 2026-03-03T16:55:22Z
  checked: Health probe via Daytona preview URL on port 18790
  found: `sandbox.get_preview_link(18790)` returned `https://18790-a5dc49e2-2bc9-4d62-b5ce-884f29ccc719.proxy.daytona.works`; `/health` returned HTTP 200 but HTML login page content.
  implication: Network path exists but request is intercepted by auth/proxy layer, not reaching Picoclaw health handler directly.

- timestamp: 2026-03-03T16:55:56Z
  checked: Step 4 bridge POST against preview URL host (with and without preview token)
  found: Both requests reached `daytonaproxy01.net` and returned HTTP 404 `Not found.` for `/bridge/run`.
  implication: Ingress is reachable but target route is absent at backend on port 18790 (or wrong path/service bound).

- timestamp: 2026-03-03T16:56:32Z
  checked: Step 5 direct execution inside sandbox via `sandbox.process.exec`
  found: Commands run successfully (`exit_code=0`), process list shows `/usr/local/bin/daytona picoclaw`, and listeners are `2280`, `22220`, `22222`, `33333` (no `18790`).
  implication: Sandbox is alive, but expected bridge listener on `18790` is absent.

- timestamp: 2026-03-03T16:57:31Z
  checked: Preview-link probes on active ports (`2280`, `22220`, `22222`, `33333`)
  found: All ports return HTTP 200 HTML login page on `/health` and HTTP 404 on `/bridge/run` (with and without token).
  implication: Daytona proxy ingress is reachable, but Picoclaw bridge route is unavailable behind it.

- timestamp: 2026-03-03T16:58:07Z
  checked: In-sandbox runtime process/listener/workspace validation
  found: No agent/minerva/python/node process signatures, no listener on port `18790`, `/home/daytona/workspace` missing, and only `/workspace/pack` mount present.
  implication: Sandbox is started at Daytona layer but Picoclaw runtime was not hydrated/bootstrapped for this instance.

## Resolution
root_cause:
  Daytona workspace `a5dc49e2-2bc9-4d62-b5ce-884f29ccc719` is orphaned from local orchestrator state and never finished Picoclaw runtime hydration. DB has no `sandbox_instances` row, provider's static gateway derivation points to non-existent host, and in-sandbox checks show no bridge/agent process or 18790 listener.
fix:
  No code change applied. Operational fix is to recreate/rebind sandbox through orchestrator so DB row, hydration workflow, workspace path setup, and bridge startup occur atomically.
verification:
  Verified Daytona control plane reachability (`AsyncDaytona.get` succeeds) and sandbox command execution (`process.exec` works) while all bridge-path checks fail (`/bridge/run` 404, no 18790 listener), isolating failure to Picoclaw orchestration/hydration layer.
files_changed: []
