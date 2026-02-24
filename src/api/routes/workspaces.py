"""Workspace management endpoints.

Provides endpoints for workspace bootstrap and sandbox resolution
with durable workspace continuity across sessions.
"""

from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies.auth import resolve_principal_or_guest, AnyPrincipal
from src.db.session import get_db
from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
from src.guest.identity import is_guest_principal


router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


def _get_principal_user_id(principal: AnyPrincipal) -> UUID:
    """Extract and normalize principal user_id to UUID.

    Raises HTTPException if user_id is missing or invalid.
    """
    user_id = getattr(principal, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid principal identity",
                "reason": "Principal has no user_id",
            },
        )

    # Normalize string UUID to UUID object
    if isinstance(user_id, str):
        try:
            return UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid principal identity",
                    "reason": "user_id is not a valid UUID",
                },
            )

    if isinstance(user_id, UUID):
        return user_id

    # Unexpected type
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "Invalid principal identity",
            "reason": f"user_id has unexpected type: {type(user_id).__name__}",
        },
    )


# Request/Response Models


class WorkspaceBootstrapResponse(BaseModel):
    """Response when bootstrapping a workspace."""

    workspace_id: str = Field(..., description="Unique workspace identifier")
    name: str = Field(..., description="Workspace name")
    created: bool = Field(
        ..., description="True if workspace was created, False if reused"
    )
    message: str = Field(..., description="Status message")


class SandboxResolveResponse(BaseModel):
    """Response when resolving sandbox for a workspace."""

    workspace_id: str = Field(..., description="Workspace identifier")
    sandbox_id: Optional[str] = Field(
        None, description="Sandbox identifier if resolved"
    )
    state: str = Field(..., description="Sandbox state (ready, hydrating, etc.)")
    health: Optional[str] = Field(None, description="Sandbox health status")
    lease_acquired: bool = Field(..., description="Whether write lease was acquired")
    message: str = Field(..., description="Resolution message")


class SandboxResolveError(BaseModel):
    """Response for sandbox resolution failures."""

    workspace_id: str = Field(..., description="Workspace identifier")
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error")
    action: Optional[str] = Field(None, description="Recommended action")


class WorkspaceStatusResponse(BaseModel):
    """Response for workspace status."""

    workspace_id: str = Field(..., description="Workspace identifier")
    name: str = Field(..., description="Workspace name")
    is_active: bool = Field(..., description="Whether workspace is active")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


# Endpoints


@router.post(
    "/bootstrap",
    response_model=WorkspaceBootstrapResponse,
    status_code=status.HTTP_200_OK,
    summary="Bootstrap workspace",
    description="Ensure durable workspace exists for the authenticated principal. Creates if needed, reuses if exists.",
    responses={
        403: {"description": "Guest mode not allowed", "model": Dict[str, str]},
    },
)
async def bootstrap_workspace(
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> WorkspaceBootstrapResponse:
    """Bootstrap a durable workspace for the authenticated principal.

    This endpoint ensures the user has a workspace that persists across
    sessions. If no workspace exists, it creates one. If a workspace
    exists, it returns the existing one.

    Guest principals cannot bootstrap workspaces - they use ephemeral
    non-persistent sandboxes.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Guest mode does not support workspace bootstrap",
                "reason": "Guest sessions are ephemeral and do not have persistent workspaces",
            },
        )

    # Initialize lifecycle service
    lifecycle = WorkspaceLifecycleService(session=db)

    # Ensure workspace exists (auto-create if needed)
    workspace = await lifecycle.ensure_workspace(principal)

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to create or resolve workspace",
                "reason": "Workspace creation failed unexpectedly",
            },
        )

    # Determine if this is a new workspace or an existing one
    # We can detect this by checking if the workspace was just created
    # (created_at and updated_at are very close)
    from datetime import datetime, timezone

    created_recently = (workspace.updated_at - workspace.created_at).total_seconds() < 5

    message = (
        "Workspace created successfully"
        if created_recently
        else "Workspace already exists and is ready"
    )

    return WorkspaceBootstrapResponse(
        workspace_id=str(workspace.id),
        name=workspace.name,
        created=created_recently,
        message=message,
    )


@router.post(
    "/{workspace_id}/sandbox/resolve",
    response_model=SandboxResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve sandbox",
    description="Resolve active healthy sandbox or provision/hydrate replacement with lease acquisition.",
    responses={
        403: {"description": "Access denied", "model": SandboxResolveError},
        404: {"description": "Workspace not found", "model": SandboxResolveError},
        409: {"description": "Lease conflict", "model": SandboxResolveError},
    },
)
async def resolve_sandbox(
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> SandboxResolveResponse:
    """Resolve sandbox target for a workspace.

    This endpoint:
    1. Acquires a write lease for the workspace
    2. Resolves an active healthy sandbox if one exists
    3. Creates/hydrates a replacement if no healthy sandbox exists
    4. Returns the routing target with lease status
    """
    from uuid import uuid4
    from src.db.models import Workspace
    from src.identity.key_material import Principal

    # Validate workspace_id format
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid workspace ID format",
                "workspace_id": workspace_id,
            },
        )

    # For authenticated principals, verify workspace access
    if not is_guest_principal(principal):
        # Get workspace to verify ownership
        workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()

        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Workspace not found",
                    "workspace_id": workspace_id,
                },
            )

        # Verify the principal owns this workspace (normalized UUID comparison)
        user_id = _get_principal_user_id(principal)
        if workspace.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Access denied",
                    "reason": "You do not have access to this workspace",
                },
            )

    # Initialize lifecycle service and resolve target
    lifecycle = WorkspaceLifecycleService(session=db)
    run_id = str(uuid4())

    try:
        # For guest principals, create a temporary workspace wrapper
        if is_guest_principal(principal):
            from dataclasses import dataclass

            @dataclass
            class GuestWorkspaceContext:
                id: UUID

            # Create ephemeral context for guest
            guest_context = GuestWorkspaceContext(id=ws_uuid)
            target = await lifecycle.resolve_target(
                principal=guest_context,
                auto_create=True,
                acquire_lease=True,
                run_id=run_id,
            )
        else:
            target = await lifecycle.resolve_target(
                principal=principal,
                auto_create=True,
                acquire_lease=True,
                run_id=run_id,
            )

        # Handle errors from lifecycle resolution
        if target.error:
            if "conflict" in target.error.lower() or "lease" in target.error.lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": target.error,
                        "error_type": "lease_conflict",
                        "action": "Retry request after current operation completes",
                    },
                )

        # Map state and health to response
        state = "unknown"
        health = None
        sandbox_id = None

        if target.routing_result and target.routing_result.success:
            routing_result = target.routing_result
            if routing_result.sandbox:
                sandbox_id = str(routing_result.sandbox.id)
                # Map sandbox state to response string
                state = str(routing_result.sandbox.state.value)
                if routing_result.sandbox.health_status:
                    health = str(routing_result.sandbox.health_status.value)
            else:
                state = "provisioning"
        elif target.error:
            state = "error"

        return SandboxResolveResponse(
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            state=state,
            health=health,
            lease_acquired=target.lease_acquired,
            message=target.error if target.error else "Sandbox resolved successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": f"Failed to resolve sandbox: {str(e)}",
                "error_type": "resolution_failure",
                "action": "Contact support if issue persists",
            },
        )

    # For authenticated principals, verify workspace access
    if not is_guest_principal(principal):
        # Get workspace to verify ownership
        workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()

        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Workspace not found",
                    "workspace_id": workspace_id,
                },
            )

        # Verify the principal owns this workspace
        user_id = getattr(principal, "user_id", None)
        if workspace.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Access denied",
                    "reason": "You do not have access to this workspace",
                },
            )

    # Initialize lifecycle service and resolve target
    lifecycle = WorkspaceLifecycleService(session=db)
    run_id = str(uuid4())

    try:
        target = await lifecycle.resolve_target(
            principal=principal,
            workspace_id=ws_uuid if is_guest_principal(principal) else None,
            auto_create=True,
            acquire_lease=True,
            run_id=run_id,
        )

        # Handle errors from lifecycle resolution
        if target.error:
            if "conflict" in target.error.lower() or "lease" in target.error.lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": target.error,
                        "error_type": "lease_conflict",
                        "action": "Retry request after current operation completes",
                    },
                )

        # Map state and health to response
        state = "unknown"
        health = None
        sandbox_id = None

        if target.routing_result and target.routing_result.success:
            routing_result = target.routing_result
            if routing_result.sandbox:
                sandbox_id = str(routing_result.sandbox.id)
                # Map sandbox state to response string
                state = str(routing_result.sandbox.state.value)
                if routing_result.sandbox.health_status:
                    health = str(routing_result.sandbox.health_status.value)
            else:
                state = "provisioning"
        elif target.error:
            state = "error"

        return SandboxResolveResponse(
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            state=state,
            health=health,
            lease_acquired=target.lease_acquired,
            message=target.error if target.error else "Sandbox resolved successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": f"Failed to resolve sandbox: {str(e)}",
                "error_type": "resolution_failure",
                "action": "Contact support if issue persists",
            },
        )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceStatusResponse,
    summary="Get workspace status",
    description="Get the current status of a workspace.",
    responses={
        403: {"description": "Access denied"},
        404: {"description": "Workspace not found"},
    },
)
async def get_workspace(
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> WorkspaceStatusResponse:
    """Get workspace status.

    Returns workspace metadata and status information.
    """
    from uuid import UUID
    from src.db.models import Workspace

    # Validate workspace_id format
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid workspace ID format"},
        )

    # Get workspace
    workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Workspace not found"},
        )

    # Check access for non-guest principals (normalized UUID comparison)
    if not is_guest_principal(principal):
        user_id = _get_principal_user_id(principal)
        if workspace.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Access denied"},
            )

    return WorkspaceStatusResponse(
        workspace_id=str(workspace.id),
        name=workspace.name,
        is_active=workspace.is_active,
        created_at=workspace.created_at.isoformat() if workspace.created_at else "",
        updated_at=workspace.updated_at.isoformat() if workspace.updated_at else None,
    )


@router.get(
    "/me/status",
    response_model=WorkspaceStatusResponse,
    summary="Get current user's workspace",
    description="Get the workspace associated with the authenticated principal.",
    responses={
        403: {"description": "Guest mode not allowed"},
        404: {"description": "No workspace found"},
    },
)
async def get_my_workspace(
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> WorkspaceStatusResponse:
    """Get the current user's workspace status.

    Returns the workspace associated with the authenticated principal.
    """
    from src.db.models import Workspace

    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Guest mode does not have persistent workspaces",
                "reason": "Guest sessions are ephemeral",
            },
        )

    # Get normalized user ID (UUID type for consistent comparison)
    user_id = _get_principal_user_id(principal)

    # Get workspace (UUID-to-UUID comparison)
    workspace = db.query(Workspace).filter(Workspace.owner_id == user_id).first()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "No workspace found",
                "action": "Call POST /workspaces/bootstrap to create a workspace",
            },
        )

    return WorkspaceStatusResponse(
        workspace_id=str(workspace.id),
        name=workspace.name,
        is_active=workspace.is_active,
        created_at=workspace.created_at.isoformat() if workspace.created_at else "",
        updated_at=workspace.updated_at.isoformat() if workspace.updated_at else None,
    )
