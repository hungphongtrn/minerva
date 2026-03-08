---
phase: 02-workspace-lifecycle-and-agent-pack-portability
plan: 02
type: summary
subsystem: infrastructure
success: true
completed: 2026-02-24
---

# Phase 2 Plan 2: Provider Adapter Boundary - Summary

## One-Liner
Implemented sandbox provider adapter abstraction enabling equivalent semantics across local Docker Compose and Daytona BYOC profiles with config-driven selection and 24 parity test assertions.

## What Was Built

### Provider Protocol and Base Models (`src/infrastructure/sandbox/providers/base.py`)
- **SandboxState enum**: Semantic lifecycle states (READY, HYDRATING, UNHEALTHY, STOPPED, STOPPING, UNKNOWN)
- **SandboxHealth enum**: Health status (HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN)
- **SandboxRef**: Provider-agnostic reference with metadata
- **SandboxInfo**: Complete state snapshot with workspace binding
- **SandboxConfig**: Provisioning configuration including TTL and env vars
- **Exception hierarchy**: SandboxProviderError, NotFoundError, ProvisionError, ConfigurationError, ProfileError
- **Abstract SandboxProvider**: 6-method contract
  - `get_active_sandbox()` - Query active sandbox for workspace
  - `provision_sandbox()` - Create/restore with HYDRATING→READY transition
  - `get_health()` - Fresh health check (fail-closed)
  - `stop_sandbox()` - Idempotent termination
  - `attach_workspace()` - Bind workspace to sandbox
  - `update_activity()` - TTL tracking

### Local Docker Compose Adapter (`src/infrastructure/sandbox/providers/local_compose.py`)
- In-memory state registry for development/testing
- Deterministic provider ref generation from workspace UUID
- Simulated async lifecycle transitions
- Additional `mark_unhealthy()` for test scenarios

### Daytona Adapter (`src/infrastructure/sandbox/providers/daytona.py`)
- Support for Daytona Cloud and self-hosted BYOC modes
- Configurable base_url for custom deployments
- Daytona native state to semantic state mapping
- Cloud detection based on URL patterns
- Simulated async operations for testing

### Provider Factory (`src/infrastructure/sandbox/providers/factory.py`)
- `get_provider(profile)` - Config-driven instantiation
- `list_available_profiles()` - Discover supported profiles
- `register_provider()` - Extensibility hook for custom providers
- Fail-closed validation for unsupported profiles
- Profile-specific configuration injection

### Configuration Settings (`src/config/settings.py`)
- `SANDBOX_PROFILE` - Active profile selection
- `DAYTONA_API_TOKEN` - Authentication
- `DAYTONA_BASE_URL` - Self-hosted endpoint (empty = Cloud)
- `DAYTONA_TARGET_REGION` - Cloud region

### Parity Tests (`src/tests/services/test_sandbox_provider_adapters.py`)
24 test assertions across 4 test classes:
- **TestProviderFactory**: Profile selection, instantiation, error handling
- **TestSemanticParityLifecycle**: Cross-provider semantic equivalence
- **TestProviderSpecificBehavior**: Profile-specific features
- **TestSemanticStateTransitions**: State machine verification

## Key Decisions

### DEC-02-02-001: Semantic State Contract Over Native Payloads
**Decision**: Define provider-agnostic SandboxState/SandboxHealth enums rather than exposing provider-native states.

**Rationale**: Services must be provider-agnostic. Native Daytona states ("started", "creating") and Docker states differ; semantic abstraction ensures consistent routing logic.

**Impact**: All providers implement state mapping; routing layer depends only on semantic states.

### DEC-02-02-002: Fail-Closed Behavior for Unknown States
**Decision**: Unknown health states, missing sandboxes, and unsupported profiles raise explicit errors rather than returning default/unknown values.

**Rationale**: Security and safety - routing to unknown state could cause data leakage or execution in wrong sandbox.

**Impact**: Services must handle SandboxNotFoundError, SandboxProfileError; routing explicitly excludes unhealthy sandboxes.

### DEC-02-02-003: Idempotent Stop Operations
**Decision**: `stop_sandbox()` must be safe to call multiple times, returning STOPPED state even for non-existent sandboxes.

**Rationale**: Lease expiration, crash recovery, and TTL enforcement may all attempt stop; idempotency prevents error cascades.

**Impact**: Both adapters implement idempotent stop with terminal state tracking.

### DEC-02-02-004: Config-Driven Profile Selection
**Decision**: Profile selection via SANDBOX_PROFILE environment variable, not code branching or request-time parameters.

**Rationale**: AGNT-03 requires "switching to cloud options should primarily be environment-argument changes, not workflow changes."

**Impact**: One setting changes entire deployment profile; no route-level conditionals.

### DEC-02-02-005: Self-Hosted Daytona First-Class Support
**Decision**: Daytona adapter supports both Cloud and self-hosted via DAYTONA_BASE_URL configuration.

**Rationale**: 02-CONTEXT.md explicitly prioritizes Daytona self-host as "a handy option" alongside Cloud.

**Impact**: Empty base_url = Cloud; custom URL = self-hosted; same adapter code paths.

## Deviations from Plan

None - plan executed exactly as written.

## Test Results

```
$ uv run pytest src/tests/services/test_sandbox_provider_adapters.py -q
24 passed, 1 skipped in 0.47s
```

Test coverage:
- Provider factory configuration (5 tests)
- Semantic lifecycle parity (11 tests)
- Provider-specific behavior (4 tests)
- State transition verification (4 tests)

1 skipped: Daytona provider test requiring real API token (expected in CI without credentials).

## Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `src/infrastructure/__init__.py` | Created | Infrastructure package marker |
| `src/infrastructure/sandbox/__init__.py` | Created | Sandbox adapters package |
| `src/infrastructure/sandbox/providers/__init__.py` | Created | Providers package |
| `src/infrastructure/sandbox/providers/base.py` | Created | Protocol, DTOs, exceptions |
| `src/infrastructure/sandbox/providers/local_compose.py` | Created | Docker Compose adapter |
| `src/infrastructure/sandbox/providers/daytona.py` | Created | Daytona Cloud/self-hosted adapter |
| `src/infrastructure/sandbox/providers/factory.py` | Created | Provider instantiation |
| `src/config/settings.py` | Modified | Added sandbox profile settings |
| `src/tests/services/test_sandbox_provider_adapters.py` | Created | 24 parity assertions |

## Traceability

### Requirements Addressed
- **AGNT-03**: "The same registered agent pack runs with equivalent semantics in local Docker Compose and BYOC profiles" - Provider adapters with parity tests satisfy this.
- **WORK-01**: Workspace lifecycle foundation - Provider interface enables workspace attach operations.

### Provides Foundation For
- 02-03-PLAN.md (Workspace lifecycle services) - Services will call provider interface
- 02-05-PLAN.md (API routes) - Routes use factory to obtain configured provider

## Commits

1. `715c0a1` - feat(02-02): define sandbox provider protocol and semantic models
2. `9f2f340` - feat(02-02): implement local compose and daytona adapter classes
3. `afe0228` - feat(02-02): wire provider factory and add parity tests

## Next Phase Readiness

Phase 2 Plan 2 complete. Next plans in Phase 2:
- 02-03: Workspace lifecycle services (uses this provider interface)
- 02-04: Template scaffold and pack registration
- 02-05: API routes and SECU-05 tests

This provider boundary enables those plans to work with any supported profile without code changes.
