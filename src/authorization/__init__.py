"""Authorization module exports."""

from src.authorization.policy import (
    Action,
    ResourceType,
    Role,
    Principal,
    can_perform,
    authorize_action,
    require_workspace_access,
    get_role_from_string,
    requires_role,
)

from src.authorization.guards import (
    resolve_auth_principal,
    guard_workspace_resource,
    require_owner,
    require_admin_or_owner,
    guard_read_resource,
    guard_create_resource,
    guard_update_resource,
    guard_delete_resource,
    guard_admin_resource,
)

__all__ = [
    # Policy
    "Action",
    "ResourceType",
    "Role",
    "Principal",
    "can_perform",
    "authorize_action",
    "require_workspace_access",
    "get_role_from_string",
    "requires_role",
    # Guards
    "resolve_auth_principal",
    "guard_workspace_resource",
    "require_owner",
    "require_admin_or_owner",
    "guard_read_resource",
    "guard_create_resource",
    "guard_update_resource",
    "guard_delete_resource",
    "guard_admin_resource",
]
