# Dead Code & Legacy

**Identified cleanup opportunities and deprecated components.**

---

## Table of Contents

1. [Summary](#summary)
2. [Deprecated Services](#deprecated-services)
3. [Legacy Settings](#legacy-settings)
4. [Duplicate/Overlapping Code](#duplicateoverlapping-code)
5. [Unused Imports & Functions](#unused-imports--functions)
6. [Test Duplication](#test-duplication)
7. [Cleanup Recommendations](#cleanup-recommendations)

---

## Summary

| Category | Count | Priority |
|----------|-------|----------|
| Deprecated services | 1 | High |
| Legacy settings | 6 | Medium |
| Duplicate code blocks | 4 | Medium |
| Unused imports | ~20 | Low |
| Legacy test files | 2 | Low |

**Estimated cleanup effort:** 2-3 days
**Risk level:** Low (good test coverage)

---

## Deprecated Services

### ZeroclawGatewayService

**File:** `src/services/zeroclaw_gateway_service.py`  
**Lines:** ~650  
**Status:** ⚠️ DEPRECATED - To be consolidated

**Why it's deprecated:**
- Overlaps 80% with `SandboxGatewayService`
- Has retry logic that violates single-attempt design
- Different error categorization creates confusion

**Current usage:**
```bash
# Search for imports
grep -r "ZeroclawGatewayService" src/ --include="*.py"
```

Found in:
- `src/services/run_service.py` (indirectly via imports)
- `src/tests/services/test_zeroclaw_gateway_service.py`

**Migration path:**
1. ✅ Move token rotation logic to `SandboxGatewayService`
2. ⬜ Update `run_service.py` to use `SandboxGatewayService` only
3. ⬜ Move relevant tests to `test_sandbox_gateway_service.py`
4. ⬜ Delete `zeroclaw_gateway_service.py`

**Code to migrate:**
```python
# From ZeroclawGatewayService - move to SandboxGatewayService
def _rotate_token_if_needed(self, sandbox_id: UUID) -> GatewayTokenBundle:
    """Check and rotate expired tokens."""
    # ... token rotation logic ...
```

---

## Legacy Settings

### Daytona Configuration Aliases

**File:** `src/config/settings.py` (lines 55-72)

```python
# Backward compatibility (deprecated, use DAYTONA_API_KEY)
DAYTONA_API_TOKEN: str = ""

# Backward compatibility (deprecated, use DAYTONA_API_URL)
DAYTONA_BASE_URL: str = ""  # Line 65

# Backward compatibility (deprecated, use DAYTONA_TARGET)
DAYTONA_TARGET_REGION: str = "us"  # Line 71
```

**Cleanup:**
```python
# Replace alias resolution with:
@property
def daytona_api_key(self) -> str:
    return self.DAYTONA_API_KEY or self.DAYTONA_API_TOKEN
```

With:
```python
# Simplified - remove aliases
def daytona_api_key(self) -> str:
    return self.DAYTONA_API_KEY
```

**Impact:** Update all usages in `daytona.py` and documentation.

---

### Legacy Base Image Settings

**File:** `src/config/settings.py` (lines 93-99)

```python
DAYTONA_BASE_IMAGE_DIGEST_REQUIRED: bool = False
```

**Status:** Redundant

`DAYTONA_BASE_IMAGE_STRICT_MODE=True` already implies digest required. Remove this separate flag.

---

## Duplicate/Overlapping Code

### 1. Gateway URL Resolution

**Location 1:** `src/services/run_service.py` (lines 550-580)
```python
def _get_authoritative_sandbox_url(self, routing: RunRoutingResult) -> str:
    """Resolve authoritative URL for gateway requests."""
```

**Location 2:** `src/services/zeroclaw_gateway_service.py` (lines 150-180)
```python
def _resolve_sandbox_url(self, routing: RunRoutingResult) -> str:
    """Resolve sandbox gateway URL."""
```

**Issue:** Nearly identical logic, slightly different error handling.

**Fix:** Move to shared utility in `src/services/gateway_utils.py`.

---

### 2. Token Bundle Resolution

**Location 1:** `src/services/run_service.py` (lines 600-650)
```python
def _resolve_gateway_tokens(self, routing: RunRoutingResult, ...) -> GatewayTokenBundle:
```

**Location 2:** `src/services/zeroclaw_gateway_service.py` (lines 200-250)
```python
def _get_token_bundle(self, sandbox_id: UUID) -> GatewayTokenBundle:
```

**Fix:** Consolidate in `SandboxGatewayService` after migration.

---

### 3. Error Categorization

**Location 1:** `src/services/sandbox_gateway_service.py` - `GatewayErrorType`
```python
class GatewayErrorType:
    AUTH_ERROR = "auth_error"
    TRANSPORT_ERROR = "transport_error"
    UPSTREAM_ERROR = "upstream_error"
```

**Location 2:** `src/services/zeroclaw_gateway_service.py` - Different error types
```python
class GatewayErrorType:
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    RUNTIME = "runtime"
```

**Fix:** Standardize on `sandbox_gateway_service.py` types.

---

### 4. Bridge Output Parsing

**Location 1:** `src/api/routes/runs.py` (lines 260-290)
```python
def _extract_bridge_output(result: RunResult) -> dict:
    """Extract output from bridge execution."""
```

**Location 2:** `src/api/oss/routes/runs.py` (lines 170-220)
```python
# Inline output extraction logic
if result and hasattr(result, "outputs"):
    outputs = result.outputs
    # ... parsing logic ...
```

**Fix:** Create shared helper in `src/services/bridge_output_utils.py`.

---

## Unused Imports & Functions

### Identified via Static Analysis

**File:** `src/services/run_service.py`
```python
# Line 15 - Unused
from typing import Optional  # Already imported via __future__

# Line 28 - Potentially unused
from src.services.sandbox_gateway_service import GatewayTokenBundle
# Used only in type hints, could use TYPE_CHECKING
```

**File:** `src/services/sandbox_orchestrator_service.py`
```python
# Line 12 - Unused
import secrets  # Not used in this file
```

**File:** `src/api/routes/runs.py`
```python
# Line 8 - Unused type
from typing import Optional, Dict, Any
# Optional not used
```

**Recommendation:** Run `ruff check --select F401` to find all unused imports.

---

### Unused Functions

**File:** `src/services/run_service.py`

```python
# Lines 147-161 - Never called internally
def persist_run(self, context: RunContext) -> None:
    """Persist run record — blocked for guests."""
    # Only raises PermissionError for guests
    # No actual persistence logic
```

**Analysis:** This method only validates (raises error) but doesn't persist. The actual persistence happens in `_create_run_session()`. Consider renaming to `_validate_can_persist()`.

---

## Test Duplication

### Deprecated Test Files

**File:** `src/tests/services/test_run_service_deprecated_bridge_helpers.py`

**Lines:** ~100  
**Status:** Legacy regression tests for removed methods

**Content:**
```python
"""Regression tests for deprecated bridge helpers in RunService."""
# Tests for _is_recoverable_bridge_error - method removed
```

**Action:** ⬜ Delete this file - the methods no longer exist.

---

### Overlapping Test Coverage

**Test files with overlapping scenarios:**

1. `test_workspace_lifecycle_service.py` (lines 400-500)
   - Tests lease acquisition
   
2. `test_workspace_lease_service.py` (lines 200-300)
   - Also tests lease acquisition

**Issue:** Same scenarios tested at two levels.

**Recommendation:** Keep unit tests in `test_workspace_lease_service.py`, keep integration tests in `test_workspace_lifecycle_service.py`. Remove duplicates from lifecycle tests.

---

## Legacy Comments & TODOs

### Active TODOs

**File:** `src/api/routes/runs.py` (line 191)
```python
# Check for lease conflict (legacy check for non-routing errors)
```

**Action:** ⬜ Remove this legacy check after confirming routing layer handles all cases.

---

**File:** `src/api/oss/routes/runs.py` (line 200)
```python
# Check for final output from bridge (legacy path)
```

**Action:** ⬜ Remove once all runtimes return structured events.

---

### Outdated Comments

**File:** `src/services/preflight_service.py` (line 50)
```python
# Phase 2: Check workspace lease status
# TODO: Remove after Phase 3 migration
```

**Status:** Phase 3 is complete, this can be removed.

---

## Cleanup Recommendations

### Phase 1: Safe Removals (Low Risk)

**Files to delete:**
1. `src/tests/services/test_run_service_deprecated_bridge_helpers.py`
2. `src/tests/services/test_zeroclaw_gateway_service.py` (after migration)

**Unused imports:**
```bash
ruff check --select F401 --fix
```

**Outdated comments:**
- Remove "Phase 2" / "Phase 3" references in comments
- Update TODOs that are complete

---

### Phase 2: Service Consolidation (Medium Risk)

**Steps:**
1. Move token rotation from `ZeroclawGatewayService` to `SandboxGatewayService`
2. Update `run_service.py` to use `SandboxGatewayService` exclusively
3. Migrate relevant tests
4. Delete `ZeroclawGatewayService`
5. Update all imports

**Testing:**
- Run full test suite: `pytest src/tests/ -v`
- Run smoke tests: `pytest src/tests/smoke/ -v`
- Test gateway execution manually

---

### Phase 3: Code Deduplication (Medium Risk)

**Create shared utilities:**

```python
# src/services/gateway_utils.py
def resolve_sandbox_url(routing: RunRoutingResult) -> str:
    """Shared URL resolution logic."""
    
def resolve_gateway_tokens(
    routing: RunRoutingResult,
    session: Session
) -> GatewayTokenBundle:
    """Shared token resolution."""
```

```python
# src/services/bridge_output_utils.py
def extract_bridge_output(result: RunResult) -> Optional[dict]:
    """Extract and normalize bridge output."""
    
def map_events_to_oss_format(events: List[dict]) -> List[dict]:
    """Convert internal events to OSS format."""
```

---

### Phase 4: Settings Cleanup (Low Risk)

**Remove deprecated settings:**

```python
# src/config/settings.py

# REMOVE these lines:
DAYTONA_API_TOKEN: str = ""  # Line 55-56
DAYTONA_BASE_URL: str = ""  # Line 65-66
DAYTONA_TARGET_REGION: str = "us"  # Line 71-72
DAYTONA_BASE_IMAGE_DIGEST_REQUIRED: bool = False  # Line 93-99
```

**Update factory:**
```python
# src/infrastructure/sandbox/providers/factory.py (line 97)
# Change:
api_key=settings.DAYTONA_API_KEY or settings.DAYTONA_API_TOKEN,
# To:
api_key=settings.DAYTONA_API_KEY,
```

---

## Cleanup Checklist

### Pre-cleanup
- [ ] Create branch: `cleanup/legacy-code-removal`
- [ ] Run full test suite to establish baseline
- [ ] Review with team

### Phase 1: Safe Removals
- [ ] Delete `test_run_service_deprecated_bridge_helpers.py`
- [ ] Run `ruff check --select F401 --fix`
- [ ] Remove outdated comments
- [ ] Commit: "chore: remove unused test file and imports"

### Phase 2: Service Consolidation
- [ ] Copy token rotation to `SandboxGatewayService`
- [ ] Update `run_service.py` imports
- [ ] Migrate tests
- [ ] Delete `ZeroclawGatewayService`
- [ ] Run full test suite
- [ ] Commit: "refactor: consolidate gateway services"

### Phase 3: Deduplication
- [ ] Create `gateway_utils.py`
- [ ] Create `bridge_output_utils.py`
- [ ] Update all callers
- [ ] Run tests
- [ ] Commit: "refactor: extract shared gateway utilities"

### Phase 4: Settings
- [ ] Remove deprecated settings
- [ ] Update factory
- [ ] Update documentation
- [ ] Commit: "chore: remove deprecated settings"

### Post-cleanup
- [ ] Run full test suite
- [ ] Run smoke tests
- [ ] Update CHANGELOG
- [ ] Create PR with detailed description

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Delete test files | Low | Tests are for removed code |
| Remove imports | Low | Automated with ruff |
| Consolidate services | Medium | Comprehensive test coverage |
| Extract utilities | Low | Pure refactoring |
| Remove settings | Medium | Check production configs |

**Rollback plan:**
- All changes in single branch
- Can revert individual commits
- Database schema unchanged
