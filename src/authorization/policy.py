"""Authorization policy engine for workspace-level access control.

Defines role-based access control (RBAC) policies for workspace resources.
Supports owner, admin, and member roles with different permission sets.
"""

from enum import Enum
from typing import Optional, Set
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status


class Action(Enum):
    """Actions that can be performed on workspace resources."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ADMIN = "admin"  # Workspace management actions


class ResourceType(Enum):
    """Types of workspace resources."""

    WORKSPACE = "workspace"
    MEMBERSHIP = "membership"
    API_KEY = "api_key"
    AGENT_PACK = "agent_pack"
    WORKSPACE_RESOURCE = "workspace_resource"


class Role(Enum):
    """Workspace membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# Authorization matrix: role -> resource_type -> set of allowed actions
# Fail-closed: if not explicitly allowed, access is denied
AUTHORIZATION_MATRIX: dict[Role, dict[ResourceType, Set[Action]]] = {
    Role.OWNER: {
        ResourceType.WORKSPACE: {
            Action.READ,
            Action.UPDATE,
            Action.DELETE,
            Action.ADMIN,
        },
        ResourceType.MEMBERSHIP: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
            Action.ADMIN,
        },
        ResourceType.API_KEY: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
            Action.ADMIN,
        },
        ResourceType.AGENT_PACK: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
            Action.ADMIN,
        },
        ResourceType.WORKSPACE_RESOURCE: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
            Action.ADMIN,
        },
    },
    Role.ADMIN: {
        ResourceType.WORKSPACE: {Action.READ, Action.UPDATE},
        ResourceType.MEMBERSHIP: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },
        ResourceType.API_KEY: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },
        ResourceType.AGENT_PACK: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },
        ResourceType.WORKSPACE_RESOURCE: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },
    },
    Role.MEMBER: {
        ResourceType.WORKSPACE: {Action.READ},
        ResourceType.MEMBERSHIP: {
            Action.READ
        },  # Can see own membership only (filtered in query)
        ResourceType.API_KEY: {Action.READ, Action.CREATE},  # Can manage own keys
        ResourceType.AGENT_PACK: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },
        ResourceType.WORKSPACE_RESOURCE: {
            Action.READ,
            Action.CREATE,
            Action.UPDATE,
            Action.DELETE,
        },  # Normal workspace work
    },
}


@dataclass(frozen=True)
class Principal:
    """Authenticated principal with workspace context."""

    user_id: UUID
    workspace_id: UUID
    role: Role
    is_active: bool = True


def can_perform(role: Role, resource_type: ResourceType, action: Action) -> bool:
    """Check if a role can perform an action on a resource type.

    This is a pure function that checks the authorization matrix.

    Args:
        role: The role to check
        resource_type: Type of resource being accessed
        action: Action being attempted

    Returns:
        True if the action is allowed, False otherwise (fail-closed)
    """
    role_policies = AUTHORIZATION_MATRIX.get(role)
    if not role_policies:
        return False

    resource_policies = role_policies.get(resource_type)
    if not resource_policies:
        return False

    return action in resource_policies


def authorize_action(
    principal: Principal,
    resource_type: ResourceType,
    action: Action,
    target_workspace_id: Optional[UUID] = None,
) -> None:
    """Authorize an action by a principal on a resource.

    This is the main entry point for authorization checks. It:
    1. Verifies the principal is active
    2. Verifies workspace match (if target_workspace provided)
    3. Verifies role allows the action on the resource type

    Args:
        principal: The authenticated principal attempting the action
        resource_type: Type of resource being accessed
        action: Action being attempted
        target_workspace_id: Optional workspace ID to verify cross-workspace access

    Raises:
        HTTPException: 403 Forbidden if authorization fails
    """
    # Check principal is active
    if not principal.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Principal is inactive",
        )

    # Check workspace match if target workspace specified
    if target_workspace_id is not None:
        if principal.workspace_id != target_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to target workspace",
            )

    # Check role authorization
    if not can_perform(principal.role, resource_type, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{principal.role.value}' cannot perform '{action.value}' on '{resource_type.value}'",
        )


def require_workspace_access(principal: Principal, target_workspace_id: UUID) -> None:
    """Verify principal has access to the target workspace.

    This is a helper for explicit workspace boundary checks.

    Args:
        principal: The authenticated principal
        target_workspace_id: The workspace being accessed

    Raises:
        HTTPException: 403 Forbidden if workspaces don't match
    """
    if principal.workspace_id != target_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-workspace access denied",
        )


def get_role_from_string(role_str: str) -> Role:
    """Convert a string role to a Role enum.

    Args:
        role_str: Role string (owner, admin, member)

    Returns:
        Role enum value

    Raises:
        ValueError: If role string is invalid
    """
    try:
        return Role(role_str.lower())
    except ValueError:
        raise ValueError(
            f"Invalid role: {role_str}. Must be one of: {[r.value for r in Role]}"
        )


def requires_role(*roles: Role):
    """Decorator factory to require specific roles for an action.

    This returns a decorator that can be used to enforce role requirements.
    Note: This is for use with functions, not FastAPI dependencies.
    For FastAPI routes, use the guard functions.

    Args:
        *roles: Required roles

    Returns:
        Decorator function
    """
    allowed_roles = set(roles)

    def decorator(func):
        def wrapper(principal: Principal, *args, **kwargs):
            if principal.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requires one of roles: {[r.value for r in roles]}",
                )
            return func(principal, *args, **kwargs)

        return wrapper

    return decorator
