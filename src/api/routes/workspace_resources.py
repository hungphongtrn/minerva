"""Workspace resource API endpoints.

CRUD endpoints for workspace-scoped resources with authorization
and RLS context enforcement. Demonstrates tenant isolation and
role-based access control.

Requirements covered:
- AUTH-03: User can access only their own workspace resources
- AUTH-05: Owner/member roles produce different authorization outcomes
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.rls_context import with_rls_context
from src.db.models import Membership
from src.api.dependencies.auth import resolve_principal
from src.identity.key_material import Principal as IdentityPrincipal
from src.authorization.policy import (
    Principal as AuthPrincipal,
    Action,
    ResourceType,
    authorize_action,
    get_role_from_string,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/resources", tags=["workspace-resources"]
)


# Pydantic schemas
class WorkspaceResourceCreate(BaseModel):
    """Schema for creating a workspace resource."""

    name: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(..., min_length=1, max_length=100)
    config: Optional[str] = None


class WorkspaceResourceUpdate(BaseModel):
    """Schema for updating a workspace resource."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    config: Optional[str] = None
    is_active: Optional[bool] = None


class WorkspaceResourceResponse(BaseModel):
    """Schema for workspace resource response."""

    id: UUID
    workspace_id: UUID
    resource_type: str
    name: str
    config: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceResourceList(BaseModel):
    """Schema for listing workspace resources."""

    items: List[WorkspaceResourceResponse]
    total: int
    workspace_id: UUID


def _resolve_auth_principal_with_role(
    identity_principal: IdentityPrincipal,
    db: Session,
) -> AuthPrincipal:
    """Resolve identity principal to auth principal with role lookup.

    Queries the membership table for actual role based on user_id and workspace_id.
    Raises HTTPException with 403 if no membership is found.
    """
    from sqlalchemy import select

    user_id = UUID(identity_principal.user_id)
    workspace_id = UUID(identity_principal.workspace_id)

    # Query membership table for actual role
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.workspace_id == workspace_id,
    )
    membership = db.execute(stmt).scalar_one_or_none()

    if membership is None:
        # No membership found - deny access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Forbidden",
                "status": 403,
                "action": "access",
                "resource": "workspace_resource",
                "reason": "No workspace membership found for user",
            },
        )

    # Convert membership role string to Role enum
    role = get_role_from_string(membership.role)

    return AuthPrincipal(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        is_active=identity_principal.is_active,
    )


@router.get("", response_model=WorkspaceResourceList)
async def list_resources(
    workspace_id: UUID,
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    identity_principal: IdentityPrincipal = Depends(resolve_principal),
) -> WorkspaceResourceList:
    """List resources in a workspace.

    Demonstrates AUTH-03: Users can only access resources in their own workspace.

    Args:
        workspace_id: The workspace to list resources from
        resource_type: Optional filter by resource type
        db: Database session
        identity_principal: Authenticated principal

    Returns:
        List of resources in the workspace

    Raises:
        HTTPException: 403 if cross-workspace access attempted or no membership
    """
    from src.db.models import WorkspaceResource

    # Resolve to authorization principal using membership-backed role
    auth_principal = _resolve_auth_principal_with_role(identity_principal, db)

    # Authorize READ action on workspace resource
    authorize_action(
        principal=auth_principal,
        resource_type=ResourceType.WORKSPACE_RESOURCE,
        action=Action.READ,
        target_workspace_id=workspace_id,
    )

    # Set RLS context for tenant isolation
    with with_rls_context(
        db, workspace_id, auth_principal.user_id, auth_principal.role.value
    ):
        query = db.query(WorkspaceResource).filter(
            WorkspaceResource.workspace_id == workspace_id
        )

        if resource_type:
            query = query.filter(WorkspaceResource.resource_type == resource_type)

        resources = query.all()

    return WorkspaceResourceList(
        items=[WorkspaceResourceResponse.model_validate(r) for r in resources],
        total=len(resources),
        workspace_id=workspace_id,
    )


@router.post(
    "", response_model=WorkspaceResourceResponse, status_code=status.HTTP_201_CREATED
)
async def create_resource(
    workspace_id: UUID,
    data: WorkspaceResourceCreate,
    db: Session = Depends(get_db),
    identity_principal: IdentityPrincipal = Depends(resolve_principal),
) -> WorkspaceResourceResponse:
    """Create a new resource in a workspace.

    Demonstrates AUTH-05: Role differences (owner/admin can create, member permissions vary).

    Args:
        workspace_id: The workspace to create the resource in
        data: Resource creation data
        db: Database session
        identity_principal: Authenticated principal

    Returns:
        The created resource

    Raises:
        HTTPException: 403 if not authorized to create in workspace or no membership
    """
    from src.db.models import WorkspaceResource

    # Resolve to authorization principal using membership-backed role
    auth_principal = _resolve_auth_principal_with_role(identity_principal, db)

    # Authorize CREATE action
    authorize_action(
        principal=auth_principal,
        resource_type=ResourceType.WORKSPACE_RESOURCE,
        action=Action.CREATE,
        target_workspace_id=workspace_id,
    )

    # Create resource with RLS context
    with with_rls_context(
        db, workspace_id, auth_principal.user_id, auth_principal.role.value
    ):
        resource = WorkspaceResource(
            workspace_id=workspace_id,
            resource_type=data.resource_type,
            name=data.name,
            config=data.config,
            is_active=True,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

    return WorkspaceResourceResponse.model_validate(resource)


@router.get("/{resource_id}", response_model=WorkspaceResourceResponse)
async def get_resource(
    workspace_id: UUID,
    resource_id: UUID,
    db: Session = Depends(get_db),
    identity_principal: IdentityPrincipal = Depends(resolve_principal),
) -> WorkspaceResourceResponse:
    """Get a specific resource by ID.

    Args:
        workspace_id: The workspace containing the resource
        resource_id: The resource ID
        db: Database session
        identity_principal: Authenticated principal

    Returns:
        The resource

    Raises:
        HTTPException: 404 if not found, 403 if cross-workspace access or no membership
    """
    from src.db.models import WorkspaceResource

    # Resolve to authorization principal using membership-backed role
    auth_principal = _resolve_auth_principal_with_role(identity_principal, db)

    # Authorize READ action
    authorize_action(
        principal=auth_principal,
        resource_type=ResourceType.WORKSPACE_RESOURCE,
        action=Action.READ,
        target_workspace_id=workspace_id,
    )

    # Query with RLS context
    with with_rls_context(
        db, workspace_id, auth_principal.user_id, auth_principal.role.value
    ):
        resource = (
            db.query(WorkspaceResource)
            .filter(
                WorkspaceResource.id == resource_id,
                WorkspaceResource.workspace_id == workspace_id,
            )
            .first()
        )

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    return WorkspaceResourceResponse.model_validate(resource)


@router.patch("/{resource_id}", response_model=WorkspaceResourceResponse)
async def update_resource(
    workspace_id: UUID,
    resource_id: UUID,
    data: WorkspaceResourceUpdate,
    db: Session = Depends(get_db),
    identity_principal: IdentityPrincipal = Depends(resolve_principal),
) -> WorkspaceResourceResponse:
    """Update a resource.

    Demonstrates AUTH-05: Role differences in update permissions.

    Args:
        workspace_id: The workspace containing the resource
        resource_id: The resource ID
        data: Update data
        db: Database session
        identity_principal: Authenticated principal

    Returns:
        The updated resource

    Raises:
        HTTPException: 404 if not found, 403 if not authorized or no membership
    """
    from src.db.models import WorkspaceResource

    # Resolve to authorization principal using membership-backed role
    auth_principal = _resolve_auth_principal_with_role(identity_principal, db)

    # Authorize UPDATE action
    authorize_action(
        principal=auth_principal,
        resource_type=ResourceType.WORKSPACE_RESOURCE,
        action=Action.UPDATE,
        target_workspace_id=workspace_id,
    )

    # Query and update with RLS context
    with with_rls_context(
        db, workspace_id, auth_principal.user_id, auth_principal.role.value
    ):
        resource = (
            db.query(WorkspaceResource)
            .filter(
                WorkspaceResource.id == resource_id,
                WorkspaceResource.workspace_id == workspace_id,
            )
            .first()
        )

        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource {resource_id} not found",
            )

        # Apply updates
        if data.name is not None:
            resource.name = data.name
        if data.config is not None:
            resource.config = data.config
        if data.is_active is not None:
            resource.is_active = data.is_active

        db.commit()
        db.refresh(resource)

    return WorkspaceResourceResponse.model_validate(resource)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    workspace_id: UUID,
    resource_id: UUID,
    db: Session = Depends(get_db),
    identity_principal: IdentityPrincipal = Depends(resolve_principal),
) -> None:
    """Delete (soft-delete) a resource.

    Demonstrates AUTH-05: Only owners/admins can delete.

    Args:
        workspace_id: The workspace containing the resource
        resource_id: The resource ID
        db: Database session
        identity_principal: Authenticated principal

    Raises:
        HTTPException: 404 if not found, 403 if not authorized or no membership
    """
    from src.db.models import WorkspaceResource

    # Resolve to authorization principal using membership-backed role
    auth_principal = _resolve_auth_principal_with_role(identity_principal, db)

    # Authorize DELETE action
    authorize_action(
        principal=auth_principal,
        resource_type=ResourceType.WORKSPACE_RESOURCE,
        action=Action.DELETE,
        target_workspace_id=workspace_id,
    )

    # Query and soft-delete with RLS context
    with with_rls_context(
        db, workspace_id, auth_principal.user_id, auth_principal.role.value
    ):
        resource = (
            db.query(WorkspaceResource)
            .filter(
                WorkspaceResource.id == resource_id,
                WorkspaceResource.workspace_id == workspace_id,
            )
            .first()
        )

        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource {resource_id} not found",
            )

        # Soft delete
        resource.is_active = False
        db.commit()
