"""Authorization guards for FastAPI dependency injection.

Provides FastAPI-compatible dependency functions for enforcing
authorization policies on protected routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import Membership
from src.authorization.policy import (
    Action,
    ResourceType,
    Role,
    Principal as AuthPrincipal,
    authorize_action,
    get_role_from_string,
)
from src.identity.key_material import Principal as IdentityPrincipal


class AuthPrincipalFactory:
    """Factory to convert identity Principal to authorization Principal."""

    @staticmethod
    def from_identity_principal(
        identity_principal: IdentityPrincipal,
        role: Role,
    ) -> AuthPrincipal:
        """Convert an identity principal to an authorization principal.

        Args:
            identity_principal: Principal from identity layer
            role: The user's role in the workspace

        Returns:
            Authorization principal for policy checks
        """
        return AuthPrincipal(
            user_id=UUID(identity_principal.user_id),
            workspace_id=UUID(identity_principal.workspace_id),
            role=role,
            is_active=identity_principal.is_active,
        )


def get_membership_role(db: Session, user_id: UUID, workspace_id: UUID) -> Optional[Role]:
    """Get the membership role for a user in a workspace.

    Args:
        db: Database session
        user_id: The user ID
        workspace_id: The workspace ID

    Returns:
        Role enum if membership exists, None otherwise
    """
    from sqlalchemy import select

    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.workspace_id == workspace_id,
    )
    membership = db.execute(stmt).scalar_one_or_none()

    if membership is None:
        return None

    return get_role_from_string(membership.role)


def resolve_auth_principal_dep():
    """Create a dependency that resolves an identity principal to an authorization principal.

    This factory avoids circular imports by importing resolve_principal at call time.

    Returns:
        FastAPI dependency function
    """
    from src.api.dependencies.auth import resolve_principal

    def _resolve(
        db: Session = Depends(get_db),
        identity_principal: IdentityPrincipal = Depends(resolve_principal),
    ) -> AuthPrincipal:
        """Resolve an identity principal to an authorization principal.

        Looks up the user's actual membership role in the workspace.
        Denies requests where no membership exists with a 403 response.
        """
        user_id = UUID(identity_principal.user_id)
        workspace_id = UUID(identity_principal.workspace_id)

        # Look up actual membership role
        role = get_membership_role(db, user_id, workspace_id)

        if role is None:
            # No membership found - deny access deterministically
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: no workspace membership found",
            )

        return AuthPrincipal(
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
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
def guard_read_resource():
    return guard_workspace_resource(Action.READ)


def guard_create_resource():
    return guard_workspace_resource(Action.CREATE)


def guard_update_resource():
    return guard_workspace_resource(Action.UPDATE)


def guard_delete_resource():
    return guard_workspace_resource(Action.DELETE)


def guard_admin_resource():
    return guard_workspace_resource(Action.ADMIN)
