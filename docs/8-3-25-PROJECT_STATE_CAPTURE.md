# Minerva Project State Capture

## Created Tasks

**Epic**: `minerva-mfy` - Project State Capture and Cleanup

### Subtasks Created:

1. **`minerva-314`** - Capture and Simplify OSS Version Spec
   - Priority: High (1)
   - Status: Open
   - Consult smart-planner to simplify the goal of the OSS version

2. **`minerva-5iy`** - Establish Key Coding Standards  
   - Priority: High (1)
   - Status: Open
   - Establish patterns for Python/FastAPI, database, testing, documentation

3. **`minerva-9mx`** - Identify State Diagram and Cleanup Deadcode
   - Priority: High (1)
   - Status: In Progress
   - Architecture analysis complete (see below)

---

## Architecture Analysis Summary

### Core Value Proposition
From PROJECT.md:
> **Any team can run ZeroClaw safely for multiple users with strong isolation and predictable behavior, without building orchestration and sandbox infrastructure themselves.**

### Key Components Identified

| Component | Purpose |
|-----------|---------|
| **Run Execution** | Execute agent runs with policy enforcement |
| **Workspace Lifecycle** | Durable workspace management, auto-create, routing |
| **Sandbox Orchestration** | Health-aware routing, provisioning, TTL enforcement |
| **ZeroClaw Gateway** | Communication with in-sandbox agent runtime |
| **Agent Packs** | Pack registration, validation, scaffolding |
| **Checkpoint/Restore** | Session persistence and recovery |

### State Diagrams Identified

1. **Sandbox Lifecycle**: PENDING → CREATING → ACTIVE/UNHEALTHY → STOPPING → STOPPED/FAILED
2. **Run Execution**: QUEUED → RUNNING → EXECUTING → COMPLETED/FAILED/CANCELLED
3. **Workspace**: FREE → ACTIVE (LEASED) → RELEASED/EXPIRED

### Deadcode Cleanup Recommendations

**Immediate (Low Risk):**
- Remove `docs/archive/.planning/debug/resolved/` 
- Archive planning docs to separate repo

**Short-term (Medium Risk):**
- Consolidate gateway services (`sandbox_gateway_service.py` + `zeroclaw_gateway_service.py`)
- Remove legacy error handling paths
- Clean up deprecated bridge test files

**Long-term:**
- Centralize error types
- Consolidate documentation
- Review service vs infrastructure boundaries

### Current MVP State
- Phases 1-3.5 Complete (71% overall)
- ZeroClaw migration complete (Picoclaw removed)
- Event streaming bridge implemented
- Ready for Phase 4: Execution Orchestration

---

## Next Steps

1. **Complete Task 1** (`minerva-314`): Consult smart-planner to simplify OSS spec
2. **Complete Task 2** (`minerva-5iy`): Establish coding standards
3. **Continue Task 3** (`minerva-9mx`): Execute cleanup based on recommendations

---

*Generated: 2026-03-08*
