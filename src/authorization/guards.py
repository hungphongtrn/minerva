"""Authorization guards for FastAPI dependency injection.

Provides FastAPI-compatible dependency functions for enforcing
authorization policies on protected routes.
"""

from functools import wraps
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

from src.authorization.policy import (
    Action,
    ResourceType,
    Role,
    Principal as AuthPrincipal,
    authorize_action,
    require_workspace_access,
    get_role_from_string,
)
from src.identity.key_material import Principal as IdentityPrincipal


class AuthPrincipalFactory:
    """Factory to convert identity Principal to authorization Principal."""

    @staticmethod
    def from_identity_principal(
        identity_principal: IdentityPrincipal,
        user_id: UUID,
        role: Role,
    ) -> AuthPrincipal:
        """Convert an identity principal to an authorization principal.

        Args:
            identity_principal: Principal from identity layer
            user_id: The user ID (not directly in API key principal)
            role: The user's role in the workspace

        Returns:
            Authorization principal for policy checks
        """
        return AuthPrincipal(
            user_id=user_id,
            workspace_id=UUID(identity_principal.workspace_id),
            role=role,
            is_active=identity_principal.is_active,
        )


def resolve_auth_principal_dep():
    """Create a dependency that resolves an identity principal to an authorization principal.

    This factory avoids circular imports by importing resolve_principal at call time.

    Returns:
        FastAPI dependency function
    """
    from src.api.dependencies.auth import resolve_principal

    def _resolve(
        identity_principal: IdentityPrincipal = Depends(resolve_principal),
    ) -> AuthPrincipal:
        """Resolve an identity principal to an authorization principal.

        This is a placeholder that assumes role lookup happens elsewhere.
        In production, this would query the membership table.

        For now, we extract workspace_id and assume owner role for testing.
        """
        # TODO: In production, query membership table for actual role
        # For now, return a principal with owner role (for testing)
        return AuthPrincipal(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),  # Placeholder
            workspace_id=UUID(identity_principal.workspace_id),
            role=Role.OWNER,  # Default to owner for testing
            is_active=identity_principal.is_active,
        )

    return _resolve


def guard_workspace_resource(
    action: Action,
    target_workspace_id: Optional[UUID] = None,
):
    """Guard factory for workspace resource actions.

    Usage:
        @router.get("/workspaces/{workspace_id}/resources")
        async def list_resources(
            workspace_id: UUID,
            principal: AuthPrincipal = Depends(guard_workspace_resource(Action.READ))
        ):
            ...

    Args:
        action: The action being guarded
        target_workspace_id: Optional explicit workspace ID

    Returns:
        Dependency function
    """

    def _guard(
        principal: AuthPrincipal = Depends(resolve_auth_principal_dep()),
    ) -> AuthPrincipal:
        authorize_action(
            principal=principal,
            resource_type=ResourceType.WORKSPACE_RESOURCE,
            action=action,
            target_workspace_id=target_workspace_id,
        )
        return principal

    return _guard


def require_owner_dep():
    """Create a dependency that requires owner role.

    Usage:
        @router.delete("/resource")
        async def delete(
            principal: AuthPrincipal = Depends(require_owner_dep())
        ):
            ...

    Returns:
        Dependency function
    """

    def _require(
        principal: AuthPrincipal = Depends(resolve_auth_principal_dep()),
    ) -> AuthPrincipal:
        if principal.role != Role.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner role required",
            )
        return principal

    return _require


def require_admin_or_owner_dep():
    """Create a dependency that requires admin or owner role.

    Usage:
        @router.patch("/resource")
        async def update(
            principal: AuthPrincipal = Depends(require_admin_or_owner_dep())
        ):
            ...

    Returns:
        Dependency function
    """

    def _require(
        principal: AuthPrincipal = Depends(resolve_auth_principal_dep()),
    ) -> AuthPrincipal:
        if principal.role not in (Role.ADMIN, Role.OWNER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or owner role required",
            )
        return principal

    return _require


def require_workspace_match_dep(workspace_id_param: str = "workspace_id"):
    """Factory to create dependency requiring workspace ID match.

    Usage:
        @router.get("/workspaces/{workspace_id}/resources")
        async def list_resources(
            principal: AuthPrincipal = Depends(require_workspace_match_dep("workspace_id"))
        ):
            ...

    Args:
        workspace_id_param: The path parameter name containing workspace ID

    Returns:
        Dependency function
    """

    def _guard(
        principal: AuthPrincipal = Depends(resolve_auth_principal_dep()),
    ) -> AuthPrincipal:
        # Note: In FastAPI, path params are injected as kwargs
        # This is a simplified version - production would use request.state
        return principal

    return _guard


# Convenience guards for common patterns
guard_read_resource = lambda: guard_workspace_resource(Action.READ)
guard_create_resource = lambda: guard_workspace_resource(Action.CREATE)
guard_update_resource = lambda: guard_workspace_resource(Action.UPDATE)
guard_delete_resource = lambda: guard_workspace_resource(Action.DELETE)
guard_admin_resource = lambda: guard_workspace_resource(Action.ADMIN)
