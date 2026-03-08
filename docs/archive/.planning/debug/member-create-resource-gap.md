---
status: investigating
trigger: "Member role cannot create workspace resources; owner/admin/member outcomes must differ with deterministic role enforcement."
created: 2026-02-23T16:00:00Z
updated: 2026-02-23T16:05:00Z
---

## Current Focus

hypothesis: AUTHORIZATION_MATRIX grants CREATE permission to MEMBER role for WORKSPACE_RESOURCE
test: Review policy.py authorization matrix for MEMBER role permissions
expecting: Confirm MEMBER has CREATE permission when it should only have READ
next_action: Document root cause and affected files

## Symptoms

expected: Member POST /workspaces/{workspace_id}/resources should return 403 Forbidden
actual: Member POST /workspaces/{workspace_id}/resources returned 201 Created
errors: No error - permission check passed incorrectly
reproduction: Member user with valid API key makes POST request to create workspace resource
started: Always broken - policy matrix configured incorrectly

## Eliminated

- hypothesis: Authorization check not being called
  evidence: create_resource endpoint at line 212-218 correctly calls authorize_action with Action.CREATE
  timestamp: 2026-02-23T16:02:00Z

- hypothesis: Role resolution failing
  evidence: _resolve_auth_principal_with_role correctly queries membership table and resolves role
  timestamp: 2026-02-23T16:03:00Z

## Evidence

- timestamp: 2026-02-23T16:01:00Z
  checked: src/authorization/policy.py AUTHORIZATION_MATRIX
  found: MEMBER role at lines 121-126 has Action.CREATE, Action.UPDATE, Action.DELETE for WORKSPACE_RESOURCE
  implication: Member is incorrectly authorized to create resources

- timestamp: 2026-02-23T16:02:00Z
  checked: src/api/routes/workspace_resources.py create_resource endpoint
  found: Endpoint correctly calls authorize_action(principal, ResourceType.WORKSPACE_RESOURCE, Action.CREATE)
  implication: Authorization check is being called but policy allows the action

- timestamp: 2026-02-23T16:03:00Z
  checked: Test file comment at test_membership_role_behavior.py:69-72
  found: Test author noted "MEMBER has DELETE permission on WORKSPACE_RESOURCE" - this is documented but wrong
  implication: The incorrect permissions are known but not fixed

- timestamp: 2026-02-23T16:04:00Z
  checked: Comparison of OWNER/ADMIN vs MEMBER permissions
  found: OWNER and ADMIN have same WORKSPACE_RESOURCE permissions as MEMBER (all 4 actions)
  implication: No role differentiation exists for workspace resource mutations

## Resolution

root_cause: AUTHORIZATION_MATRIX in policy.py incorrectly grants CREATE, UPDATE, DELETE permissions to MEMBER role for WORKSPACE_RESOURCE type; should only grant READ
fix: ""
verification: ""
files_changed: []
