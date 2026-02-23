"""Whoami endpoint for authentication verification.

Provides a protected endpoint that returns the authenticated
principal information, useful for verifying API keys and
debugging authentication issues.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List

from src.api.dependencies.auth import resolve_principal, Principal


router = APIRouter(prefix="/whoami", tags=["Identity"])


class WhoamiResponse(BaseModel):
    """Response containing the authenticated principal information."""

    workspace_id: str = Field(
        ..., description="The workspace ID associated with the API key"
    )
    key_id: str = Field(
        ..., description="The unique identifier of the API key being used"
    )
    scopes: List[str] = Field(
        ..., description="Permission scopes granted to this API key"
    )
    is_active: bool = Field(..., description="Whether the API key is currently active")
    authentication_status: str = Field(
        "authenticated", description="Status of the authentication"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                "key_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "scopes": ["workspace:read", "workspace:write"],
                "is_active": True,
                "authentication_status": "authenticated",
            }
        }


class WhoamiErrorResponse(BaseModel):
    """Error response when authentication fails."""

    authentication_status: str = Field(
        "unauthenticated", description="Status indicating authentication failure"
    )
    error: str = Field(
        ..., description="Error message explaining why authentication failed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "authentication_status": "unauthenticated",
                "error": "API key required",
            }
        }


@router.get(
    "",
    response_model=WhoamiResponse,
    summary="Get current authenticated principal",
    description="""
    Returns information about the currently authenticated principal.
    
    This endpoint is protected and requires a valid API key.
    It's useful for:
    - Verifying that your API key works
    - Checking which workspace you're authenticated as
    - Viewing the scopes associated with your key
    - Debugging authentication issues
    
    ## Headers
    - **X-Api-Key**: Your API key
    - **Authorization**: Bearer token format (alternative to X-Api-Key)
    
    ## Responses
    - **200**: Successfully authenticated, returns principal info
    - **401**: Invalid, expired, or revoked API key
    """,
)
async def whoami(principal: Principal = Depends(resolve_principal)) -> WhoamiResponse:
    """Get the currently authenticated principal.

    This endpoint requires authentication via X-Api-Key header
    or Authorization: Bearer token. It returns information about
    the authenticated workspace and key.
    """
    return WhoamiResponse(
        workspace_id=principal.workspace_id,
        key_id=principal.key_id,
        scopes=principal.scopes,
        is_active=principal.is_active,
        authentication_status="authenticated",
    )


@router.get(
    "/guest",
    response_model=WhoamiResponse,
    summary="Get guest identity info",
    description="Returns guest identity information (for guest mode requests).",
)
async def whoami_guest() -> WhoamiResponse:
    """Get guest identity information.

    This endpoint provides information about the guest identity
    that would be assigned for unauthenticated requests.
    Note: This is a placeholder for future guest mode implementation.
    """
    # TODO: Implement guest identity generation
    # For now, return a placeholder indicating this is not yet implemented
    return WhoamiResponse(
        workspace_id="guest",
        key_id="guest",
        scopes=["guest"],
        is_active=True,
        authentication_status="guest",
    )
