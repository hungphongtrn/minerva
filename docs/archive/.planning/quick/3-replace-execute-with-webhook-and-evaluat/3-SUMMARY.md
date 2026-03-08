---
phase: quick-003-replace-execute-with-webhook-and-evaluat
plan: 003
subsystem: zeroclaw-gateway
dependency_graph:
  requires: []
  provides:
    - webhook-first-gateway-client
    - bidirectional-fallback
    - agent-pack-scaffold
    - e2e-probe
  affects:
    - src/services/zeroclaw_gateway_service.py
    - src/tests/services/test_zeroclaw_gateway_service.py
    - src/agent_packs/zeroclaw/
    - src/scripts/zeroclaw_webhook_e2e.py
tech_stack:
  added: []
  patterns:
    - spec-driven-route-selection
    - bidirectional-compatibility-fallback
    - fail-closed-on-non-404-errors
key_files:
  created:
    - src/agent_packs/zeroclaw/AGENT.md
    - src/agent_packs/zeroclaw/SOUL.md
    - src/agent_packs/zeroclaw/IDENTITY.md
    - src/agent_packs/zeroclaw/skills/.gitkeep
    - src/scripts/zeroclaw_webhook_e2e.py
    - .planning/quick/3-replace-execute-with-webhook-and-evaluat/3-SUMMARY.md
  modified:
    - src/services/zeroclaw_gateway_service.py
    - src/tests/services/test_zeroclaw_gateway_service.py
decisions:
  - id: Q003-D1
    text: "Bidirectional fallback: if primary is /webhook, fallback to /execute (and vice versa) for runtime compatibility"
  - id: Q003-D2
    text: "Keep fallback conditional on 404 only - other non-2xx errors fail fast per fail-closed semantics"
  - id: Q003-D3
    text: "Agent pack scaffold content is minimal and safe for OSS - no secrets or privileged URLs"
  - id: Q003-D4
    text: "E2E probe uses database query for verification rather than relying on gateway responses alone"
metrics:
  duration: "15 min"
  completed_date: "2026-03-06"
  tasks_completed: 3
  files_created: 6
  files_modified: 2
  tests_passing: 37
---

# Quick Task 003: Replace Execute with Webhook and Evaluate Summary

**One-liner:** Made /webhook the default Zeroclaw execute route with bidirectional compatibility fallback, added a registerable agent pack scaffold, and created an E2E probe for multi-user validation.

## What Was Delivered

### 1. Webhook-First Gateway Client (Task 1)

Updated `ZeroclawGatewayService._get_execute_candidate_urls()` to implement bidirectional compatibility fallback:

- **Primary route**: Always from `spec.gateway.execute_path` (default: `/webhook`)
- **Fallback logic**: 
  - If primary is `/webhook` → fallback to `/execute` (for legacy runtimes)
  - If primary is `/execute` → fallback to `/webhook` (for webhook-only runtimes)
- **Fail-closed preservation**: Fallback only triggers on 404, not on other non-2xx errors

**Files modified:**
- `src/services/zeroclaw_gateway_service.py` - Updated fallback logic
- `src/tests/services/test_zeroclaw_gateway_service.py` - Updated test defaults and added symmetric fallback test

### 2. Minimal Agent Pack Scaffold (Task 2)

Created a registerable agent pack at `src/agent_packs/zeroclaw/`:

- `AGENT.md` - Minimal agent definition for E2E testing
- `SOUL.md` - Test agent personality and behavior
- `IDENTITY.md` - Runtime requirements and metadata
- `skills/.gitkeep` - Empty skills directory for validation

The pack passes `AgentPackValidationService` requirements and is suitable for `minerva register` commands during E2E testing.

### 3. End-to-End Probe Script (Task 3)

Created `src/scripts/zeroclaw_webhook_e2e.py` as a runnable operator probe:

**Dry-run mode (default):**
- Validates imports and agent pack without needing credentials
- Prints setup instructions for live execution

**Run mode (`--run`):**
1. Sends two POST requests to `/runs` with distinct `X-User-ID` values
2. Consumes SSE streams until completion/failure
3. Queries database to assert:
   - Exactly 2 `sandbox_instances` exist
   - Each has matching `external_user_id`
   - `provider_ref` values are distinct (multi-user → multi-sandbox)

**Features:**
- JSON output support (`--json`) for CI integration
- Configurable base URL, workspace ID, and timeout
- Fail-fast with actionable error messages

## Verification Results

### Unit Tests
```
$ uv run pytest src/tests/services/test_zeroclaw_gateway_service.py -q
37 passed, 6 warnings in 3.74s
```

### Agent Pack Validation
```
$ uv run python -c "from src.services.agent_pack_validation import AgentPackValidationService; 
> r=AgentPackValidationService().validate('src/agent_packs/zeroclaw'); 
> assert r.is_valid, r.to_json()"
# Exit code 0 - validation passed
```

### E2E Probe Dry-Run
```
$ uv run python src/scripts/zeroclaw_webhook_e2e.py --dry-run
✓ All imports successful
✓ Agent pack validates
Status: READY
```

## Key Implementation Details

### Bidirectional Fallback Logic

```python
def _get_execute_candidate_urls(self, sandbox_url: str) -> list[str]:
    primary = self._get_execute_url(sandbox_url)
    
    if primary.endswith("/webhook"):
        fallback = urljoin(sandbox_url.rstrip("/") + "/", "execute")
    elif primary.endswith("/execute"):
        fallback = urljoin(sandbox_url.rstrip("/") + "/", "webhook")
    else:
        return [primary]  # Unknown path - no fallback
    
    return [primary, fallback] if primary != fallback else [primary]
```

### 404-Only Fallback Constraint

The fallback is only triggered when the primary route returns 404. Other non-2xx responses fail fast:

```python
# In execute() method:
if response.status_code == 404 and url_idx == 0 and len(execute_urls) > 1:
    continue  # Try fallback

# 4xx errors (except 404 with fallback) return immediately:
if 400 <= response.status_code < 500:
    return GatewayResult(success=False, error=last_error)
```

## Deviations from Plan

None - plan executed exactly as written.

## Truths Honored

1. **Zeroclaw gateway client uses POST /webhook as the default execute route.** ✓
   - `spec.json` has `"execute_path": "/webhook"`
   - Service uses spec-driven route selection
   - Tests updated to use `/webhook` as default

2. **If a sandbox runtime exposes only one of /webhook or /execute, Minerva still completes the request via compatibility fallback.** ✓
   - Bidirectional fallback implemented
   - Unit tests cover both `/execute` → `/webhook` and `/webhook` → `/execute` scenarios

3. **An operator can run an end-to-end probe that sends 2 distinct X-User-ID requests and observes 2 distinct sandbox instances.** ✓
   - `zeroclaw_webhook_e2e.py` provides runnable probe
   - Validates multi-user → multi-sandbox via database assertions

## Commits

| Hash | Message |
|------|---------|
| `fbc6acc` | feat(quick-003): make gateway execution webhook-first with bidirectional fallback |
| `ba187b9` | feat(quick-003): add minimal Zeroclaw agent pack scaffold |
| `6c506d6` | feat(quick-003): add Zeroclaw webhook E2E probe script |

## Artifacts Created

### Source Files
- `src/services/zeroclaw_gateway_service.py` (modified)
- `src/tests/services/test_zeroclaw_gateway_service.py` (modified)
- `src/agent_packs/zeroclaw/AGENT.md` (created)
- `src/agent_packs/zeroclaw/SOUL.md` (created)
- `src/agent_packs/zeroclaw/IDENTITY.md` (created)
- `src/agent_packs/zeroclaw/skills/.gitkeep` (created)
- `src/scripts/zeroclaw_webhook_e2e.py` (created)

### Documentation
- `.planning/quick/3-replace-execute-with-webhook-and-evaluat/3-SUMMARY.md` (this file)

## Next Steps

The E2E probe is ready for use when:
1. Infrastructure is configured (Daytona credentials)
2. Server is running (`uv run minerva serve`)
3. Database is accessible

Run the probe with:
```bash
uv run python src/scripts/zeroclaw_webhook_e2e.py --run
```
