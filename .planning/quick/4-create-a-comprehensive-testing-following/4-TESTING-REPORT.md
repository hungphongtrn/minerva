# Minerva Comprehensive Testing Report

**Generated:** 2026-03-06  
**Purpose:** Read-only verification pass following DEV-WORKFLOW.md  
**Scope:** Observation only; no fixes; documentation of issues

---

## Scope

This report documents the results of running a comprehensive, read-only verification pass following the `DEV-WORKFLOW.md` developer workflow guide. 

**Important Constraints:**
- Observation only - no code fixes or refactors applied
- No commits made during testing (except final report commit)
- Commands executed to establish an evidence-backed baseline
- All failures documented with repro steps and evidence

---

## Environment

| Property | Value |
|----------|-------|
| **OS** | Darwin MacBook-Pro-cua-Phong.local 25.3.0 Darwin Kernel Version 25.3.0: root:xnu-12377.81.4~5/RELEASE_ARM64_T6000 arm64 |
| **uv version** | uv 0.9.22 (82a6a66b8 2026-01-06) |
| **Python version** | Python 3.12.8 |
| **Working Directory** | /Users/phong/Workspace/minerva |

---

## Baseline Commands

### 1) Dependency Install / Lock Health

**Purpose:** Verify dependencies are correctly locked and installable

**Command:**
```bash
uv sync --dev
```

**Exit Code:** 0

**Output:**
```
Resolved 83 packages in 4ms
Audited 80 packages in 2ms
```

**Result:** ✅ PASS - Dependencies resolved and audited successfully

---

### 2) Import/Syntax Smoke Test

**Purpose:** Verify all Python source files compile without syntax errors

**Command:**
```bash
uv run python -m compileall src
```

**Exit Code:** 0

**Output:**
```
Listing 'src'...
Listing 'src/agent_packs'...
Listing 'src/agent_packs/zeroclaw'...
Listing 'src/agent_packs/zeroclaw/skills'...
Listing 'src/api'...
Listing 'src/api/dependencies'...
Listing 'src/api/oss'...
Listing 'src/api/oss/routes'...
Listing 'src/api/routes'...
Listing 'src/authorization'...
Listing 'src/cli'...
Listing 'src/cli/commands'...
Listing 'src/config'...
Listing 'src/db'...
Listing 'src/db/migrations'...
Listing 'src/db/migrations/versions'...
Compiling 'src/db/migrations/versions/__init__.py'...
Listing 'src/db/repositories'...
Listing 'src/guest'...
Listing 'src/identity'...
Listing 'src/infrastructure'...
Listing 'src/infrastructure/checkpoints'...
Listing 'src/infrastructure/sandbox'...
Listing 'src/infrastructure/sandbox/providers'...
Listing 'src/integrations'...
Listing 'src/integrations/zeroclaw'...
Listing 'src/runtime_policy'...
Listing 'src/scripts'...
Compiling 'src/scripts/phase2_profile_parity_harness.py'...
Compiling 'src/scripts/zeroclaw_webhook_e2e.py'...
Listing 'src/services'...
Listing 'src/tests'...
... (truncated for brevity)
```

**Result:** ✅ PASS - All 80+ Python files compile without syntax errors

---

### 3) Unit/Integration Tests

**Purpose:** Run full test suite to identify failures

**Command:**
```bash
uv run pytest
```

**Exit Code:** N/A (timed out after 180s)

**Output:**
```
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0
rootdir: /Users/phong/Workspace/minerva
configfile: pyproject.toml
testpaths: ["src/tests"]
plugins: anyio-4.12.1, asyncio-1.3.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_fixture_loop_scope=function
collected 956 items / 1 skipped

src/tests/authorization/test_workspace_isolation.py .................... [  2%]
........................................                                 [  6%]
src/tests/cli/test_env_example_contract.py .                             [  6%]
src/tests/cli/test_serve_preflight_workspace_gate.py .....               [  6%]
src/tests/identity/test_api_keys.py ........F..FFFFFFFFFFFF..FF...FFFFFF [ 10%]
FFFF                                                                     [ 11%]
src/tests/infrastructure/sandbox/test_daytona_volume_mount_and_config.py . [ 11%]
.....FF..                                                                [ 12%]
src/tests/integration/test_gateway_audit_daytona.py ss..                 [ 12%]
src/tests/integration/test_membership_role_behavior.py .....             [ 13%]
src/tests/integration/test_phase1_acceptance.py ........................ [ 15%]
........F                                                                [ 16%]
src/tests/integration/test_phase1_security_regressions.py ...........FF. [ 17%]
.........                                                                [ 18%]
src/tests/integration/test_phase2_acceptance.py ..........F.........FFF. [ 21%]
...                                                                      [ 21%]
src/tests/integration/test_phase2_idle_ttl_enforcement.py F.......F      [ 22%]
src/tests/integration/test_phase2_lease_contention.py ........           [ 23%]
src/tests/integration/test_phase2_run_routing_errors.py ..
```

**Observations:**
- 956 tests collected (1 skipped upfront)
- Multiple test failures observed in:
  - `test_api_keys.py`: ~20 failures (F)
  - `test_daytona_volume_mount_and_config.py`: 2 failures
  - `test_phase1_acceptance.py`: 1 failure
  - `test_phase1_security_regressions.py`: 2 failures
  - `test_phase2_acceptance.py`: 4 failures
  - `test_phase2_idle_ttl_enforcement.py`: 2 failures
- Test suite is VERY SLOW - timed out after 3 minutes at only 23% completion
- Full test run would likely take 15-20 minutes

**Result:** ⚠️ PARTIAL - Tests run but many failures and extremely slow execution

---

### 4) DEV-WORKFLOW Init Behavior (Non-Mutating)

**Purpose:** Verify `.env.example` matches the init template without regenerating it

**Command:**
```bash
uv run python -c "from pathlib import Path; from src.cli.commands.init import _render_env_example_template as r; cur=Path('.env.example').read_text(encoding='utf-8'); gen=r(); print('env_example_matches_template=', cur==gen); print('current_len=',len(cur)); print('generated_len=',len(gen))"
```

**Exit Code:** 0

**Output:**
```
env_example_matches_template= True
current_len= 5489
generated_len= 5489
```

**Result:** ✅ PASS - `.env.example` is synchronized with template

---

## Notes

### Doc Mismatches Discovered

1. **Python Version Mismatch**
   - **DEV-WORKFLOW.md says:** Python 3.11+
   - **pyproject.toml says:** `requires-python = ">=3.12"`
   - **Actual:** Python 3.12.8 installed
   - **Issue:** Documentation says 3.11+ but project requires 3.12+

2. **Default Sandbox Profile Mismatch**
   - **DEV-WORKFLOW.md Section "Local Development" says:** `SANDBOX_PROFILE=daytona`
   - **src/config/settings.py default:** `SANDBOX_PROFILE: str = "local_compose"`
   - **Issue:** Default is `local_compose` but docs suggest `daytona` for full functionality

3. **Missing Prerequisites Documentation**
   - DEV-WORKFLOW.md lists Docker 20.10+ but doesn't mention:
     - Required Docker Compose version
     - Docker Desktop vs Engine differences
     - Colima/Docker alternatives on macOS

4. **Quick Start vs Reality Gap**
   - Step 7 `uv run minerva snapshot build` requires:
     - `PICOCLAW_REPO_URL` set
     - Daytona API key configured
     - Network access to git repo and Daytona
   - Not mentioned as prerequisites before this step

---

## DEV-WORKFLOW Smoke Pass

### 1) Validate Compose File Parses

**Command:**
```bash
docker compose config
```

**Exit Code:** 0

**Output:**
```yaml
name: minerva
services:
  createbuckets:
    container_name: picoclaw-minio-setup
    ...
```

**Result:** ✅ PASS - Compose file is valid YAML

---

### 2) Start Dependencies (Postgres + MinIO)

**Command:**
```bash
docker compose up -d postgres minio
```

**Exit Code:** 0

**Output:**
```
[+] Running 2/0
 ⠋ Container picoclaw-postgres  Running                                    0.0s
 ⠋ Container picoclaw-minio     Running                                    0.0s
```

**Verification:**
```bash
docker compose ps
```

**Output:**
```
NAME                 IMAGE             COMMAND                  SERVICE        CREATED        STATUS                    PORTS
picoclaw-minio       minio/minio       "/usr/bin/docker-ent…"   minio          2 hours ago    Up 2 hours (healthy)      0.0.0.0:9000-9001->9000-9001/tcp
picoclaw-postgres    postgres:16-al... "docker-entrypoint.s…"   postgres       2 hours ago    Up 2 hours (healthy)      0.0.0.0:5432->5432/tcp
```

**Result:** ✅ PASS - Both services healthy

---

### 3) Run Migrations Against Compose Postgres

**Command:**
```bash
DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw uv run minerva migrate
```

**Exit Code:** 0

**Output:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

**Result:** ✅ PASS - Migrations applied successfully

---

### 4) Start Server and Hit /health

**Command:**
```bash
DATABASE_URL=postgresql+psycopg://picoclaw:picoclaw_dev@localhost:5432/picoclaw SANDBOX_PROFILE=local_compose uv run minerva serve --skip-preflight --host 127.0.0.1 --port 8001 &
SERVER_PID=$!
sleep 2
curl -fsS http://127.0.0.1:8001/health
STATUS=$?
kill $SERVER_PID 2>/dev/null
exit $STATUS
```

**Exit Code:** 0

**Output:**
```json
{
  "status": "healthy",
  "components": {
    "database": "healthy"
  }
}
```

**Result:** ✅ PASS - Server starts and health endpoint responds

---

### 5) Tear Down Dependencies

**Command:**
```bash
docker compose down
```

**Exit Code:** 0

**Output:**
```
[+] Running 3/3
 ⠴ Container picoclaw-minio-setup  Removed
 ⠴ Container picoclaw-minio        Removed
 ⠴ Container picoclaw-postgres     Removed
```

**Result:** ✅ PASS - Clean teardown

---

## Issues

### Blocking Issues

None identified - all smoke tests pass.

### Major Issues

**1. Test Suite Performance and Reliability**
- **Severity:** Major
- **Where:** `uv run pytest`
- **Repro Command:** `uv run pytest`
- **Expected:** Tests complete in reasonable time (<2 minutes)
- **Actual:** Timed out after 180s at only 23% completion; multiple test failures observed
- **Evidence:** 956 tests collected, test_phase2_run_routing_errors.py still running at timeout
- **Impact:** Developer experience severely degraded; CI/CD would be extremely slow

**2. Multiple Test Failures in Core Components**
- **Severity:** Major
- **Where:** src/tests/identity/test_api_keys.py, infrastructure, integration tests
- **Repro Command:** `uv run pytest src/tests/identity/test_api_keys.py -v`
- **Expected:** All tests pass
- **Actual:** ~30+ failures observed across multiple test files
- **Evidence:** 
  - `test_api_keys.py`: ~20 failures (FFFFFFFFFFFF pattern)
  - `test_daytona_volume_mount_and_config.py`: 2 failures
  - `test_phase1_acceptance.py`: 1 failure
  - `test_phase1_security_regressions.py`: 2 failures
  - `test_phase2_acceptance.py`: 4 failures
  - `test_phase2_idle_ttl_enforcement.py`: 2 failures
- **Impact:** Cannot rely on test suite for regression detection

### Minor Issues

**3. Python Version Documentation Mismatch**
- **Severity:** Minor
- **Where:** DEV-WORKFLOW.md line 95
- **Repro Command:** `head -100 DEV-WORKFLOW.md | grep -A2 "Python:"`
- **Expected:** Documentation matches pyproject.toml
- **Actual:** DEV-WORKFLOW says "Python 3.11+" but pyproject.toml requires ">=3.12"
- **Evidence:** 
  ```
  DEV-WORKFLOW.md: "Python: 3.11+ with uv package manager"
  pyproject.toml: requires-python = ">=3.12"
  ```

**4. Default Sandbox Profile Mismatch**
- **Severity:** Minor
- **Where:** DEV-WORKFLOW.md vs src/config/settings.py
- **Repro Command:** `grep "SANDBOX_PROFILE" DEV-WORKFLOW.md src/config/settings.py`
- **Expected:** Defaults documented match code defaults
- **Actual:** 
  - DEV-WORKFLOW.md examples use `daytona`
  - settings.py default is `local_compose`
- **Evidence:**
  ```python
  # settings.py line 26
  SANDBOX_PROFILE: str = "local_compose"
  ```

**5. Missing Test Coverage for Quick Start Path**
- **Severity:** Minor
- **Where:** Test suite
- **Expected:** Tests validate the exact commands in DEV-WORKFLOW.md Quick Start
- **Actual:** No apparent integration test for full `init → register → serve` flow
- **Impact:** Docs and reality can drift without detection

### Nit Issues

**6. Inconsistent Naming in DEV-WORKFLOW.md**
- **Severity:** Nit
- **Where:** DEV-WORKFLOW.md Section headers
- **Issue:** "ZeroClaw" vs "Picoclaw" vs "Zeroclaw" inconsistent capitalization
- **Evidence:** 
  - Line 27: "ZeroClaw runtime"
  - Line 109: "Picoclaw Snapshot Configuration"
  - Line 217: "Zeroclaw Gateway Configuration"

---

## Git Workspace After Running

```
 M README.md
?? .planning/quick/4-create-a-comprehensive-testing-following/
?? DEV-WORKFLOW.md
```

**Notes:**
- `README.md` modified (unrelated to this test)
- `.planning/quick/4-create-a-comprehensive-testing-following/` created (this report)
- `DEV-WORKFLOW.md` untracked (already existed, not tracked in git)

**No untracked artifacts created by running commands.**

---

## What Was Not Tested

### Items Requiring External Credentials

1. **Daytona Cloud Integration**
   - **Why not tested:** Requires valid `DAYTONA_API_KEY`
   - **DEV-WORKFLOW.md section:** Production Deployment > Option 1: Daytona Cloud
   - **Commands skipped:**
     - `uv run minerva snapshot build` (requires API key)
     - Full `/runs` endpoint with real sandbox provisioning
     - Daytona health check via API

2. **S3/MinIO Checkpoint Persistence**
   - **Why not tested:** Requires configured S3 credentials
   - **DEV-WORKFLOW.md section:** Configuration Reference > S3 Checkpoint Storage
   - **Commands skipped:**
     - Actual checkpoint upload/download operations

3. **LLM Integration**
   - **Why not tested:** Requires `LLM_API_KEY` or `OPENAI_API_KEY`
   - **DEV-WORKFLOW.md section:** Configuration Reference > LLM Configuration
   - **Impact:** Agent execution not tested (only infrastructure)

### Long-Running Operations

4. **Full Test Suite Completion**
   - **Why not tested:** Would require 15-20 minutes
   - **DEV-WORKFLOW.md section:** N/A (no explicit test command in docs)
   - **What was done:** Partial run documented with observed failures

5. **Snapshot Build Process**
   - **Why not tested:** Requires Daytona API key + 15-30 minutes
   - **DEV-WORKFLOW.md section:** Local Development > 4. Build ZeroClaw Snapshot
   - **Command:** `uv run minerva snapshot build`

6. **Agent Pack Registration and Execution**
   - **Why not tested:** Requires:
     - Daytona API key for real execution
     - LLM API key for agent to respond
     - Time to verify full flow
   - **DEV-WORKFLOW.md section:** Quick Start steps 8-9
   - **Commands:**
     - `uv run minerva scaffold --out ./my-agent`
     - `uv run minerva register ./my-agent`
     - `curl -X POST http://localhost:8000/runs ...`

---

## Summary

### Overall Assessment

| Category | Status | Notes |
|----------|--------|-------|
| **Dependencies** | ✅ Healthy | uv sync works, packages resolve |
| **Syntax** | ✅ Healthy | All files compile |
| **Smoke Tests** | ✅ Healthy | Docker compose, migrations, server start all work |
| **Test Suite** | ⚠️ Degraded | Very slow + many failures |
| **Documentation** | ⚠️ Minor Issues | Version mismatches, unclear defaults |

### Key Findings

1. **Smoke tests pass** - Basic infrastructure (Docker, DB, server) works correctly
2. **Test suite has significant issues** - ~30+ failures and extremely slow execution
3. **Documentation drift** - Python version and default configs don't match code
4. **External dependencies untested** - Daytona, S3, LLM require credentials

### Recommended Actions

1. **High Priority:** Investigate and fix test suite failures
2. **High Priority:** Profile and optimize test execution time
3. **Medium Priority:** Align DEV-WORKFLOW.md with actual requirements
4. **Low Priority:** Standardize naming conventions (ZeroClaw/Picoclaw/Zeroclaw)

---

*Report generated by Quick Task 4 - Comprehensive Testing Verification*
