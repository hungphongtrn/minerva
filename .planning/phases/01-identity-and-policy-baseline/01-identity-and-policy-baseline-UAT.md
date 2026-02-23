---
status: diagnosed
phase: 01-identity-and-policy-baseline
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
  - 01-04-SUMMARY.md
  - 01-05-SUMMARY.md
  - 01-06-SUMMARY.md
  - 01-07-SUMMARY.md
  - 01-08-SUMMARY.md
started: 2026-02-23T14:51:09Z
updated: 2026-02-23T15:57:07Z
---

## Current Test

[testing complete]

## Tests

### 1. Personal API key authentication
expected: With a valid personal API key, protected endpoints succeed for that workspace; invalid/revoked/expired keys return 401.
result: pass

### 2. API key lifecycle (rotate and revoke)
expected: Rotating a key immediately invalidates the old key material while the new key works; revoking a key blocks all subsequent authenticated requests.
result: pass

### 3. Workspace isolation boundaries
expected: A user can read/write their own workspace resources, but cross-workspace access is denied with 403 (not 500/runtime SQL failure).
result: pass

### 4. Membership-backed role behavior
expected: Owner/admin/member roles produce different API outcomes (for example create/update/delete permissions differ), and users without membership get deterministic 403 denials.
result: issue
reported: "Member POST /workspaces/{workspace_id}/resources returned 201 Created; expected 403 for member role."
severity: major

### 5. Guest mode and persistence guard
expected: Requests without explicit user identity run in guest mode with ephemeral identity and do not persist workspace state/checkpoints.
result: pass

### 6. Default-deny runtime policy enforcement
expected: Disallowed egress/tool requests are blocked before success with deterministic denied responses (HTTP 403 with parseable error details including action/resource/reason), while explicitly allowed actions succeed.
result: pass

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Member role cannot create workspace resources; owner/admin/member outcomes must differ with deterministic role enforcement."
  status: failed
  reason: "User reported: Member POST /workspaces/{workspace_id}/resources returned 201 Created; expected 403 for member role."
  severity: major
  test: 4
  root_cause: "AUTHORIZATION_MATRIX grants member CREATE/UPDATE/DELETE on workspace resources; create endpoint enforces policy correctly but policy itself is too permissive."
  artifacts:
    - path: "src/authorization/policy.py"
      issue: "MEMBER role includes Action.CREATE, Action.UPDATE, and Action.DELETE for WORKSPACE_RESOURCE."
    - path: "src/api/routes/workspace_resources.py"
      issue: "create_resource correctly calls authorize_action(Action.CREATE), but permissive policy allows member create."
  missing:
    - "Remove Action.CREATE, Action.UPDATE, and Action.DELETE from MEMBER permissions on WORKSPACE_RESOURCE in AUTHORIZATION_MATRIX."
    - "Keep only Action.READ for MEMBER on WORKSPACE_RESOURCE to enforce observable owner/admin/member differences."
  debug_session: ".planning/debug/member-create-resource-gap.md"
