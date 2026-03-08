"""Authorization module exports."""

from src.authorization.guards import (
    AuthPrincipalFactory,
    guard_admin_resource,
    guard_create_resource,
    guard_delete_resource,
    guard_read_resource,
    guard_update_resource,
    guard_workspace_resource,
    require_admin_or_owner_dep,
    require_owner_dep,
    require_workspace_match_dep,
    resolve_auth_principal_dep,
)
from src.authorization.policy import (
    Action,
    Principal,
    ResourceType,
    Role,
    authorize_action,
    can_perform,
    get_role_from_string,
    require_workspace_access,
    requires_role,
)

__all__ = [
    # Policy
    "Action",
    "AuthPrincipalFactory",
    "Principal",
    "ResourceType",
    "Role",
    "authorize_action",
    "can_perform",
    "get_role_from_string",
    "guard_admin_resource",
    "guard_create_resource",
    "guard_delete_resource",
    "guard_read_resource",
    "guard_update_resource",
    "guard_workspace_resource",
    "require_admin_or_owner_dep",
    "require_owner_dep",
    "require_workspace_access",
    "require_workspace_match_dep",
    "requires_role",
    # Guards
    "resolve_auth_principal_dep",
]
