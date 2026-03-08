# Phase 1: Identity and Policy Baseline - Research

**Researched:** 2026-02-23  
**Domain:** API key authentication, tenant isolation, RBAC, runtime policy enforcement  
**Confidence:** HIGH

## Summary

Phase 1 should use a layered security baseline: authenticate requests with API keys at the API edge, enforce tenant and role authorization in application policy checks, and enforce data isolation in Postgres via Row-Level Security (RLS). This aligns directly with AUTH-01/02/03/05/06 and gives a concrete default-deny model for SECU-01/02/03.

The standard implementation pattern is: FastAPI dependency extracts key -> key validator resolves principal (user or guest) -> request context sets tenant/role/mode -> policy engine evaluates action/tool/network/secret scope -> Postgres session context + RLS enforce row isolation. This avoids trusting app code alone for tenant boundaries.

For runtime controls, default-deny must be explicit at two layers: (1) infra/network sandbox egress defaults to blocked, and (2) app-level policy checks gate tool execution and secret injection per run. Guest mode should be ephemeral by design: random identity, no persistent keys, no workspace persistence writes.

**Primary recommendation:** Use FastAPI + Postgres RLS + explicit policy evaluation middleware, with API keys stored as one-way hashes and per-request identity context propagated into DB session settings.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.131.0 | API layer + dependency-based authn/authz | Native security dependencies (`APIKeyHeader`) and clear request dependency graph |
| SQLAlchemy | 2.0.46 | DB access + transaction scoping | Well-supported session lifecycle patterns for per-request DB work |
| psycopg | 3.3.3 | PostgreSQL driver | Modern Postgres driver for SQLAlchemy 2.0 stack |
| PostgreSQL | 18.x (or 16+) | Source-of-truth data + RLS policies | Built-in row security with default-deny when enabled and no policy matches |
| Alembic | 1.18.4 | Schema and policy migrations | Standard migration path for tables, indexes, and policy SQL |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| casbin (PyCasbin) | 1.43.0 | Role/function authorization decisions | Use for owner/member + action matrix at app layer |
| pydantic-settings | 2.13.1 | Secure, typed config loading | Use for policy defaults and environment-backed security config |
| Python `secrets` stdlib | Python 3.14 docs current | CSPRNG token generation | Use for API key material and guest identity IDs |
| Python `hmac.compare_digest` | Python 3.14 docs current | Timing-safe comparison | Use whenever comparing secret-derived values |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyCasbin RBAC model | OPA/Rego service | OPA is stronger for distributed policy-as-code, but heavier for Phase 1 bootstrap |
| DB-shared schema + RLS | schema-per-tenant | Higher tenant isolation but higher operational overhead early |
| API key auth only | OAuth2/JWT user sessions | Better for end-user auth flows, but not required for AUTH-01 baseline |

**Installation:**
```bash
uv add fastapi sqlalchemy psycopg alembic casbin pydantic-settings
```

## Architecture Patterns

### Recommended Project Structure
```text
src/
├── api/                    # FastAPI routers and dependency wiring
├── identity/               # API key issuance/rotation/revocation and principal resolution
├── authorization/          # Role + policy evaluation (owner/member, tool/network/secret gates)
├── db/                     # SQLAlchemy session setup, RLS context setters, migrations glue
├── runtime_policy/         # Egress/tool/secret policy models and enforcement hooks
└── guest/                  # Guest identity generation and persistence bypass rules
```

### Pattern 1: API Key Dependency + Principal Context
**What:** Resolve API key via `APIKeyHeader`, validate, map to principal context used by all downstream checks.
**When to use:** Every authenticated API request path.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/reference/security/
from fastapi import Depends
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

async def resolve_principal(raw_key: str | None = Depends(api_key_header)):
    # If key missing -> guest principal
    # If key present -> validate, resolve user/workspace/role
    ...
```

### Pattern 2: Session-Scoped Tenant Context + RLS
**What:** Set per-transaction identity context (workspace/user) and rely on RLS policies as hard boundary.
**When to use:** Every DB transaction serving tenant data.
**Example:**
```sql
-- Source: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;

CREATE POLICY workspace_isolation ON workspaces
USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid);
```

### Pattern 3: Default-Deny Runtime Policy Gate
**What:** Evaluate egress/tool/secret permissions before execution; deny unless explicit allow.
**When to use:** Every run start and every tool/network/secret access attempt.
**Example:**
```python
# Source (default-deny principle):
# - https://www.postgresql.org/docs/current/ddl-rowsecurity.html (default deny when no policy)
# - https://docs.docker.com/engine/network/ and /engine/network/drivers/none/

def authorize_runtime_action(ctx, action):
    # deny by default
    decision = policy_engine.evaluate(ctx, action)
    if not decision.allowed:
        raise PermissionError("policy_denied")
```

### Anti-Patterns to Avoid
- **App-only tenant filtering:** Relying only on ORM WHERE clauses without RLS allows accidental cross-tenant leaks.
- **Plaintext API keys in DB:** Store only hashed/derived key material; display secret only at issuance time.
- **Implicit allow defaults:** Policy systems that default to allow violate SECU-01/02/03 intent.
- **Single global secret bag:** Injecting all secrets into all runs breaks scoped-secret requirement.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API key extraction/parsing | Manual header parsing in every endpoint | FastAPI `APIKeyHeader` dependency | Centralized behavior, OpenAPI integration, fewer auth edge-case bugs |
| Tenant isolation only in app code | Ad hoc query filters everywhere | Postgres RLS policies + session context | Database-enforced boundary, default-deny fallback |
| Role authorization matrix | Scattered `if role == ...` checks | Casbin model/policy files | Centralized, testable policy evaluation |
| Secret lifecycle controls | Custom secret store in app DB | Managed secret backend interface (Vault/cloud secret manager abstraction) | Rotation/revocation/audit complexity is high |
| Constant-time compare logic | Hand-written timing-safe compare | `hmac.compare_digest` | Correct, vetted constant-time behavior |

**Key insight:** Identity and policy code fails most often at edge conditions and drift; standardized primitives reduce silent authorization gaps.

## Common Pitfalls

### Pitfall 1: RLS appears enabled but owner bypasses it
**What goes wrong:** Table owners (or bypass roles) can still read rows unless forced.
**Why it happens:** Default Postgres behavior allows owner bypass.
**How to avoid:** Use `FORCE ROW LEVEL SECURITY` on protected tables and avoid app connections with bypass roles.
**Warning signs:** Integration tests pass for admin role but fail to catch cross-tenant reads from service account.

### Pitfall 2: Revoked key still works due to cache staleness
**What goes wrong:** Revoked keys continue briefly due to stale in-memory auth cache.
**Why it happens:** Revocation path not coupled to cache invalidation/version check.
**How to avoid:** Use short TTL + revocation version check in DB on every request path that uses cache.
**Warning signs:** AUTH-02 tests flaky right after revoke action.

### Pitfall 3: Guest mode writes persistent records
**What goes wrong:** Anonymous requests create durable rows/checkpoints.
**Why it happens:** Guest identity tagged but persistence guard missing.
**How to avoid:** Enforce `guest_mode => no persistence writes` at service boundary, not only UI/API layer.
**Warning signs:** Non-null `guest_user_id` appears in persistent run/history tables.

### Pitfall 4: Tool allowlist not applied uniformly
**What goes wrong:** Some execution paths bypass allowlist checks.
**Why it happens:** Policy check exists only in high-level flow, not per tool invocation.
**How to avoid:** Gate every tool execution callsite with a single shared authorizer.
**Warning signs:** One-off internal tools execute even when policy says deny.

### Pitfall 5: Network default-deny is not truly default
**What goes wrong:** Containers still have outbound internet via default bridge/NAT.
**Why it happens:** Docker defaults allow outbound connectivity unless explicitly isolated.
**How to avoid:** Use explicit isolated network mode (`none` or equivalent deny egress policy) and allowlist only required destinations.
**Warning signs:** Sandbox can `curl` external endpoints in a supposedly restricted run.

## Code Examples

Verified patterns from official sources:

### FastAPI API Key Header Dependency
```python
# Source: https://fastapi.tiangolo.com/reference/security/
from fastapi import Depends, FastAPI
from fastapi.security import APIKeyHeader

app = FastAPI()
key_scheme = APIKeyHeader(name="x-api-key")

@app.get("/secure")
async def secure_endpoint(key: str = Depends(key_scheme)):
    return {"key_present": bool(key)}
```

### Postgres RLS Default-Deny Baseline
```sql
-- Source: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
-- If no applicable policy exists, table access is default-deny.

CREATE POLICY runs_tenant_policy ON runs
USING (workspace_id = current_setting('app.workspace_id', true)::uuid)
WITH CHECK (workspace_id = current_setting('app.workspace_id', true)::uuid);
```

### Transaction-Local Context for RLS
```sql
-- Source: https://www.postgresql.org/docs/current/functions-admin.html
SELECT set_config('app.workspace_id', '00000000-0000-0000-0000-000000000000', true);
-- third arg true => setting only for current transaction
```

### Cryptographically Strong Token Generation
```python
# Source: https://docs.python.org/3/library/secrets.html
import secrets

api_key_plaintext = secrets.token_urlsafe(32)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| App-layer tenant filtering only | App-layer checks + DB-enforced RLS | Became mainstream in SaaS security post-2019 | Stronger guardrail against accidental data leaks |
| Long-lived shared secrets | Scoped, short-lived, centrally managed secrets | Broadly adopted in cloud-native era | Lower blast radius and easier revocation |
| Role checks spread in handlers | Centralized policy engine evaluation | Ongoing shift in modern backend architectures | Better consistency and auditability |
| Open egress by default | Default-deny egress + explicit allowlist | Standard hardening expectation in modern runtimes | Reduced SSRF/exfiltration risk |

**Deprecated/outdated:**
- Storing credentials/API keys plaintext in application DB rows.
- Treating network policy as optional hardening after core auth is done.

## Open Questions

1. **Single DB role with RLS vs per-user DB roles**
   - What we know: RLS works with either, and single app role is operationally simpler.
   - What's unclear: Required audit granularity for DB-level actor attribution in this project.
   - Recommendation: Start with single app role + app-level audit fields; revisit if compliance scope expands.

2. **Policy engine boundary for SECU-02/03**
   - What we know: Casbin cleanly models owner/member action rules.
   - What's unclear: Whether future phases need richer attribute/context policies beyond RBAC.
   - Recommendation: Encapsulate policy calls behind an internal interface so OPA migration remains possible.

3. **Network enforcement mechanism across local Docker Compose and BYOC**
   - What we know: Docker default bridge allows outbound; explicit isolation is required.
   - What's unclear: Final BYOC substrate (Kubernetes, VM, ECS) for production policy primitives.
   - Recommendation: Define platform-agnostic policy contract now; implement per-profile adapters later.

## Sources

### Primary (HIGH confidence)
- https://fastapi.tiangolo.com/reference/security/ - `APIKeyHeader`, auth dependency behavior
- https://www.postgresql.org/docs/current/ddl-rowsecurity.html - RLS semantics, default-deny, owner bypass details
- https://www.postgresql.org/docs/current/sql-createpolicy.html - policy command behavior (`USING`, `WITH CHECK`, command scope)
- https://www.postgresql.org/docs/current/functions-admin.html - `set_config` and transaction-local setting semantics
- https://docs.python.org/3/library/secrets.html - secure token generation guidance
- https://docs.python.org/3/library/hmac.html#hmac.compare_digest - timing-safe compare guidance
- https://docs.docker.com/engine/network/ - default container networking behavior
- https://docs.docker.com/engine/network/drivers/none/ - complete network isolation mode

### Secondary (MEDIUM confidence)
- https://docs.sqlalchemy.org/en/20/orm/session_basics.html - session/transaction scoping patterns
- https://casbin.org/docs/overview - RBAC/ABAC capability and Python support overview
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html - one-way hashing and algorithm guidance
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html - scoped access, rotation, and lifecycle practices
- https://owasp.org/API-Security/editions/2023/en/0x11-t10/ - API risk model for authz/authn prioritization

### Tertiary (LOW confidence)
- Ecosystem synthesis from search aggregation for 2026 stack trends (used only for directional validation, not normative decisions).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - anchored to official docs and current package/version checks
- Architecture: HIGH - directly supported by FastAPI + Postgres official semantics
- Pitfalls: HIGH - grounded in official behavior (RLS, Docker networking, secret handling references)

**Research date:** 2026-02-23  
**Valid until:** 2026-03-25 (30 days)
