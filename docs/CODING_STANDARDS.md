# Coding Standards (Minerva)

- Purpose: keep new code consistent with existing `src/` patterns; optimize for correctness, multi-tenant safety, and operability.
- Scope: Python 3.12+, FastAPI, SQLAlchemy (sync `Session`), pytest, Alembic.

## General Principles

- Prefer clear boundaries: `src/api/` (HTTP) -> `src/services/` (business logic) -> `src/db/repositories/` (data access).
- Fail closed for security-sensitive defaults (tokens/URLs/identity readiness) and make allow-lists explicit; see `src/db/repositories/sandbox_instance_repository.py` and related tests.
- Make cleanup deterministic: acquire/release leases and resources in all branches; see `src/services/run_service.py` and `src/services/workspace_lifecycle_service.py`.
- Keep error semantics stable: return/raise errors with a machine-readable `error_type` and a human remediation hint when appropriate; see `src/api/routes/persistence.py`.
- Optimize for testability: inject dependencies (services/repos/enforcers) rather than using hidden globals; see `RunService.__init__` in `src/services/run_service.py`.

## Python Patterns

- Type hints:
  - Required for all public functions/methods and all FastAPI route signatures.
  - Use Python 3.12 syntax (`str | None`, `list[str]`, `dict[str, Any]`) as in `src/services/run_service.py`.
  - Prefer domain dataclasses for internal flow objects (e.g. `RunContext`, `RunResult` in `src/services/run_service.py`).
- Async/await:
  - Route handlers are `async def` by default (e.g. `start_run` in `src/api/routes/runs.py`).
  - Service methods are `async` only when they await I/O (gateway/provider calls); keep pure computation and DB-only helpers sync.
  - Do not call blocking network/file operations directly inside `async` routes; put them behind a service that can be awaited.
- Error handling:
  - Services should raise domain-specific exceptions (preferred) or return structured result objects (existing pattern: `RunResult`).
  - API layer maps domain failures to `HTTPException` with consistent shape; see structured `detail={"error", "error_type", "remediation"}` in `src/api/routes/persistence.py`.
  - Only swallow broad exceptions in best-effort cleanup paths; otherwise log and re-raise.
- Imports:
  - Use Ruff/isort ordering: stdlib, third-party, first-party (`src...`).
  - Prefer explicit imports at module top; use local/dynamic imports only to avoid cycles or expensive/optional deps (several existing local imports are in `src/services/run_service.py`).
  - Avoid importing from `__pycache__` artifacts; never commit `*.pyc`.

## FastAPI Patterns

- Router organization:
  - One feature per module under `src/api/routes/` with `router = APIRouter(prefix=..., tags=[...])`; see `src/api/routes/persistence.py` and `src/api/routes/runs.py`.
  - Aggregate routing in `src/api/router.py` and keep it declarative (include routers only).
  - OSS/operator endpoints live separately and mount at root; see `src/main.py` usage of `src/api/oss/router.py`.
- Dependency injection:
  - DB session: always via `db: Session = Depends(get_db)` using `src/db/session.py#get_db`.
  - Auth: prefer dependencies in `src/api/dependencies/auth.py` (`resolve_principal`, `resolve_principal_or_guest`, `require_scopes`, `require_non_guest`).
  - Keep dependencies side-effect free except for validation and principal/session resolution.
- Response models:
  - Define request/response `pydantic.BaseModel` classes near endpoints with `Field(..., description=...)` to keep OpenAPI useful; see `StartRunRequest`/`StartRunResponse` in `src/api/routes/runs.py`.
  - Use `response_model=...` consistently; return model instances (preferred) rather than raw dicts.
  - For list endpoints, prefer `List[Model]` or a wrapper model with `count` and `items` (existing: `CheckpointListResponse` in `src/api/routes/persistence.py`).
- Error response standards:
  - Use `HTTPException` with:
    - `status_code`: correct semantics (`401` auth, `403` forbidden, `404` missing, `409` conflict, `5xx` infrastructure).
    - `detail`: dict with `error`, `error_type`, and optional `remediation`; see multiple endpoints in `src/api/routes/persistence.py`.
  - When mapping internal error types to HTTP, keep a single mapping function; see `_map_routing_error` in `src/api/routes/runs.py`.
  - For `401`, include `WWW-Authenticate: Bearer` when using bearer-style auth; see `src/api/dependencies/auth.py`.

## Database Patterns

- SQLAlchemy model conventions:
  - Declarative base lives in `src/db/session.py`.
  - Table names are plural snake_case (e.g. `run_sessions`, `sandbox_instances`) in `src/db/models.py`.
  - Primary keys are UUIDs by default (`UUID(as_uuid=True)` + `default=uuid4`).
  - Prefer server-safe defaults and explicit `nullable=`; see `created_at`/`updated_at` patterns in `src/db/models.py`.
  - Enums: current code uses string constant classes + SQLAlchemy `Enum(...)` columns (e.g. `SandboxState`, `RunSessionState` in `src/db/models.py`). Keep enum values stable (migrations depend on them).
- Repository pattern:
  - Repositories live in `src/db/repositories/`, accept `Session` in `__init__`, and expose focused query/mutation methods; see `SandboxInstanceRepository` in `src/db/repositories/sandbox_instance_repository.py`.
  - Repositories may `add()` and `flush()` but should not `commit()`; commit is owned by the request/service boundary (see transaction boundaries below).
  - Query style: prefer SQLAlchemy `select()` + `scalars()` for simple queries; see `get_by_id` and `list_*` methods in `src/db/repositories/sandbox_instance_repository.py`.
- Transaction boundaries:
  - API request boundary commits on success and rolls back on exception via `src/db/session.py#get_db`.
  - Service-layer operations should assume they run inside an existing transaction and avoid calling `session.commit()`.
  - If a service must commit early (rare), document why and isolate the behavior (current exception: `_create_workspace_for_user` commits in `src/services/workspace_lifecycle_service.py`).
- Migration practices (Alembic):
  - Migrations live in `src/db/migrations/versions/` with zero-padded numeric revisions (`0001_...py`, `0008_...py`).
  - Each migration includes a top docstring describing intent and constraints; see `src/db/migrations/versions/0008_enforce_unique_user_active_sandbox.py`.
  - Prefer reversible operations; provide a `downgrade()` that cleanly removes created DB objects.
  - For advanced PostgreSQL features (partial indexes, etc.), use `op.execute(...)` with clear SQL and `IF EXISTS/IF NOT EXISTS` guards.

## Testing Standards

- Naming and location:
  - Tests live under `src/tests/` and follow `test_*.py` naming (enforced by `pyproject.toml` pytest config).
  - Organize by intent: `src/tests/services/`, `src/tests/integration/`, `src/tests/smoke/`, `src/tests/authorization/`.
- Structure:
  - Prefer Arrange/Act/Assert or Given/When/Then comments for readability; see `src/tests/services/test_sandbox_instance_repository.py`.
  - Keep tests deterministic: fixed IDs, fixed timestamps (or assert within small ranges), no real network.
- Fixtures:
  - Centralize shared integration fixtures in `conftest.py`; see `src/tests/integration/conftest.py`.
  - When using `TestClient`, use a file-based SQLite DB and override `get_db` to preserve production commit/rollback semantics; see `client` fixture in `src/tests/integration/conftest.py`.
- Mocking:
  - Use `unittest.mock.AsyncMock` for awaited methods and patch using import paths as imported by the system under test; see `src/tests/services/test_run_service_lease_release.py`.
  - Prefer mocking at system boundaries (provider/gateway/network) rather than internal helpers.
- Coverage expectations:
  - Target: >= 80% line coverage overall; >= 90% for security- and isolation-critical modules (`src/api/dependencies/`, `src/services/run_service.py`, `src/db/repositories/`).
  - Add regression tests for every bug fix and for every new error mapping / policy guard.

## Documentation Requirements

- Docstrings:
  - Required for modules, public classes, and public methods.
  - Use a consistent format with a one-line summary plus `Args:`, `Returns:`, `Raises:` where relevant; see `src/api/dependencies/auth.py`.
- README requirements:
  - Must document: local setup, required env vars, running the API, and running tests.
  - Use `uv` for Python execution (project convention): `uv run pytest`.
- API documentation:
  - Every route must have `summary` and (when non-trivial) `description` in decorator; see `src/api/routes/runs.py` and `src/api/routes/persistence.py`.
  - Request/response models should include `Field` descriptions for OpenAPI clarity.
  - Document non-200/201 responses using `responses={...}` where behavior is meaningful.
- Architecture Decision Records (ADRs):
  - Record notable, non-obvious decisions (e.g., lease model, gateway single-attempt rule, guest persistence guards).
  - Store as `docs/adr/0001-<slug>.md` with: Context, Decision, Consequences, Alternatives.

## Code Review Checklist

- Boundaries: API layer does HTTP concerns only; services own business rules; repositories own DB access.
- Types: public APIs are fully type hinted; new complex data uses dataclasses or Pydantic models.
- Errors: `HTTPException.detail` includes stable `error_type` for clients; status codes match semantics.
- Security: multi-tenant scoping is enforced (workspace_id filters, scope checks, guest restrictions).
- Transactions: no unexpected `commit()` in repositories; request boundary owns commits; rollbacks happen on errors.
- Cleanup: leases/resources are released deterministically (especially in failure branches).
- Tests: new behavior is covered; mocks are at boundaries; flaky timing assertions avoided.
- Migrations: schema changes include Alembic migration with reversible downgrade and stable enum/index naming.
- Style: Ruff/formatting conventions followed (line length 99, double quotes) per `pyproject.toml`.
