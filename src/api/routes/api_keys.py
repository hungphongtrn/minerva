"""API key lifecycle management endpoints.

Provides endpoints for creating, listing, rotating, and revoking
API keys for workspace authentication.
"""

from uuid import UUID
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.identity.service import ApiKeyService, KeyInfo
from src.identity.key_material import KeyPair
from src.api.dependencies.auth import resolve_principal, Principal


router = APIRouter(prefix="/api-keys", tags=["API Keys"])


# Request/Response Models


class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable name for the key"
    )
    scopes: List[str] = Field(default=[], description="Permission scopes for this key")
    expires_at: datetime | None = Field(
        default=None, description="Optional expiration timestamp"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Production Deployment Key",
                "scopes": ["workspace:read", "workspace:write"],
                "expires_at": None,
            }
        }


class CreateApiKeyResponse(BaseModel):
    """Response containing the new API key (only shown once)."""

    id: str = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Key name")
    full_key: str = Field(..., description="The full API key (SHOW THIS ONLY ONCE)")
    prefix: str = Field(..., description="Key prefix for identification")
    scopes: List[str] = Field(..., description="Granted scopes")
    expires_at: datetime | None = Field(..., description="Expiration timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    user_id: str = Field(..., description="User ID this key belongs to")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production Deployment Key",
                "full_key": "pk_v1_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "prefix": "pk_v1_xxxx",
                "scopes": ["workspace:read", "workspace:write"],
                "expires_at": None,
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class ApiKeyInfoResponse(BaseModel):
    """Response containing API key metadata (without sensitive data)."""

    id: str = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Key name")
    prefix: str = Field(..., description="Key prefix for identification")
    scopes: List[str] = Field(..., description="Granted scopes")
    is_active: bool = Field(..., description="Whether the key is active")
    expires_at: datetime | None = Field(..., description="Expiration timestamp")
    last_used_at: datetime | None = Field(..., description="Last usage timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    user_id: str = Field(..., description="User ID this key belongs to")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production Deployment Key",
                "prefix": "pk_v1_xxxx",
                "scopes": ["workspace:read"],
                "is_active": True,
                "expires_at": None,
                "last_used_at": "2024-01-15T12:00:00Z",
                "created_at": "2024-01-15T10:30:00Z",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        }


class RotateApiKeyResponse(BaseModel):
    """Response containing the rotated API key (only shown once)."""

    id: str = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Key name")
    full_key: str = Field(..., description="The new full API key (SHOW THIS ONLY ONCE)")
    prefix: str = Field(..., description="New key prefix")
    scopes: List[str] = Field(..., description="Granted scopes")
    is_active: bool = Field(..., description="Whether the key is active")
    rotated_at: datetime = Field(..., description="Rotation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production Deployment Key",
                "full_key": "pk_v1_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
                "prefix": "pk_v1_yyyy",
                "scopes": ["workspace:read"],
                "is_active": True,
                "rotated_at": "2024-01-15T14:00:00Z",
            }
        }


class RevokeApiKeyResponse(BaseModel):
    """Response confirming key revocation."""

    id: str = Field(..., description="Unique key identifier")
    name: str = Field(..., description="Key name")
    prefix: str = Field(..., description="Key prefix")
    is_active: bool = Field(..., description="Will be False for revoked keys")
    revoked_at: datetime = Field(..., description="Revocation timestamp")
    message: str = Field(..., description="Status message")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production Deployment Key",
                "prefix": "pk_v1_xxxx",
                "is_active": False,
                "revoked_at": "2024-01-15T15:00:00Z",
                "message": "API key has been revoked and cannot be used for authentication",
            }
        }


# Helper functions


def _key_info_to_response(key_info: KeyInfo) -> ApiKeyInfoResponse:
    """Convert KeyInfo to API response model."""
    return ApiKeyInfoResponse(
        id=key_info.id,
        name=key_info.name,
        prefix=key_info.prefix,
        scopes=key_info.scopes,
        is_active=key_info.is_active,
        expires_at=key_info.expires_at,
        last_used_at=key_info.last_used_at,
        created_at=key_info.created_at,
        user_id=key_info.user_id,
    )


# Endpoints


@router.post(
    "",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description="Create a new API key for the authenticated workspace. The full key is returned only once.",
)
async def create_api_key(
    request: CreateApiKeyRequest,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> CreateApiKeyResponse:
    """Create a new API key for the current workspace."""
    service = ApiKeyService(db)

    try:
        key_pair, key_info = service.create_key(
            workspace_id=UUID(principal.workspace_id),
            user_id=UUID(principal.user_id),
            name=request.name,
            scopes=request.scopes,
            expires_at=request.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CreateApiKeyResponse(
        id=key_info.id,
        name=key_info.name,
        full_key=key_pair.full_key,
        prefix=key_info.prefix,
        scopes=key_info.scopes,
        expires_at=key_info.expires_at,
        created_at=key_info.created_at,
        user_id=key_info.user_id,
    )


@router.get(
    "",
    response_model=List[ApiKeyInfoResponse],
    summary="List API keys",
    description="List all active API keys for the authenticated workspace.",
)
async def list_api_keys(
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
    include_inactive: bool = False,
) -> List[ApiKeyInfoResponse]:
    """List API keys for the current workspace."""
    service = ApiKeyService(db)

    keys = service.list_keys(
        workspace_id=UUID(principal.workspace_id), active_only=not include_inactive
    )

    return [_key_info_to_response(k) for k in keys]


@router.get(
    "/{key_id}",
    response_model=ApiKeyInfoResponse,
    summary="Get API key details",
    description="Get details for a specific API key.",
)
async def get_api_key(
    key_id: UUID,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> ApiKeyInfoResponse:
    """Get details for a specific API key."""
    service = ApiKeyService(db)

    key_info = service.get_key(key_id=key_id, workspace_id=UUID(principal.workspace_id))

    if key_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"API key not found: {key_id}"
        )

    return _key_info_to_response(key_info)


@router.post(
    "/{key_id}/rotate",
    response_model=RotateApiKeyResponse,
    summary="Rotate an API key",
    description="Rotate an API key, immediately invalidating the old key and returning a new one.",
)
async def rotate_api_key(
    key_id: UUID,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> RotateApiKeyResponse:
    """Rotate an API key, invalidating the old key material immediately."""
    service = ApiKeyService(db)

    try:
        key_pair, key_info = service.rotate_key(
            key_id=key_id, workspace_id=UUID(principal.workspace_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RotateApiKeyResponse(
        id=key_info.id,
        name=key_info.name,
        full_key=key_pair.full_key,
        prefix=key_info.prefix,
        scopes=key_info.scopes,
        is_active=key_info.is_active,
        rotated_at=datetime.utcnow(),
    )


@router.post(
    "/{key_id}/revoke",
    response_model=RevokeApiKeyResponse,
    summary="Revoke an API key",
    description="Revoke an API key, preventing further authentication. This cannot be undone.",
)
async def revoke_api_key(
    key_id: UUID,
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> RevokeApiKeyResponse:
    """Revoke an API key, preventing further use."""
    service = ApiKeyService(db)

    try:
        key_info = service.revoke_key(
            key_id=key_id, workspace_id=UUID(principal.workspace_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RevokeApiKeyResponse(
        id=key_info.id,
        name=key_info.name,
        prefix=key_info.prefix,
        is_active=key_info.is_active,
        revoked_at=datetime.utcnow(),
        message="API key has been revoked and cannot be used for authentication",
    )
