"""External identity dependency for OSS gateway passthrough.

This module provides authentication for OSS end-user requests where the
developer's gateway handles authentication and passes the user ID via
the X-User-ID header. Minerva trusts this header as an opaque identifier.

CRITICAL: End-users NEVER create rows in the developer `users` table.
All end-user identities are resolved to the developer's workspace via
MINERVA_WORKSPACE_ID and stored in the separate `external_identities` table.
"""

from typing import NamedTuple, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import ExternalIdentity, Workspace, AgentPack
from src.config.settings import settings


class ExternalPrincipal(NamedTuple):
    """Principal for OSS end-user requests via gateway passthrough.

        The gateway authenticates the end-user and sets X-User-ID header.
        Minerva treats this as an opaque string and resolves all end-users
    to the developer's workspace (MINERVA_WORKSPACE_ID).

        CRITICAL: End-users do NOT have User records. They use external_identities.
    """

    workspace_id: str  # UUID string from MINERVA_WORKSPACE_ID (developer's workspace)
    external_user_id: str  # The X-User-ID value from the gateway (opaque)
    is_guest: bool = False  # True when X-User-ID matches GUEST_ID
    is_active: bool = True


async def resolve_external_principal(
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: Session = Depends(get_db),
) -> ExternalPrincipal:
    """Resolve X-User-ID header to an external principal with workspace.

    This dependency:
    1. Requires MINERVA_WORKSPACE_ID to be configured (returns 403 if not set)
    2. Requires X-User-ID header (returns 400 if missing)
    3. Enforces length validation (400 if > 255 chars)
    4. Checks for guest user (no DB operations for guests)
    5. Upserts into external_identities table for non-guests
    6. Returns ExternalPrincipal with workspace_id and external_user_id

    CRITICAL SECURITY INVARIANT:
    - End-users NEVER touch the `users` table
    - All end-users resolve to the developer's workspace (MINERVA_WORKSPACE_ID)
    - Workspace-scoped uniqueness: (workspace_id, external_user_id) is unique

    Args:
        x_user_id: User ID from X-User-ID header (set by gateway)
        db: Database session

    Returns:
        ExternalPrincipal with workspace_id, external_user_id, is_guest

    Raises:
        HTTPException: 403 if MINERVA_WORKSPACE_ID not configured
                      400 if X-User-ID header is missing or too long
    """
    # Require MINERVA_WORKSPACE_ID to be configured
    if not settings.MINERVA_WORKSPACE_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MINERVA_WORKSPACE_ID not configured. Run `minerva register` to get your workspace ID, then set MINERVA_WORKSPACE_ID in your environment.",
        )

    # Require X-User-ID header
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID header required. Gateway must authenticate user.",
        )

    # Enforce database length bounds (255 chars)
    if len(x_user_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID exceeds maximum length of 255 characters.",
        )

    # Guest check: no DB operations for guests
    if settings.GUEST_ID and x_user_id == settings.GUEST_ID:
        return ExternalPrincipal(
            workspace_id=settings.MINERVA_WORKSPACE_ID,
            external_user_id=x_user_id,
            is_guest=True,
            is_active=True,
        )

    # Non-guest: upsert into external_identities table
    try:
        workspace_uuid = UUID(settings.MINERVA_WORKSPACE_ID)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid MINERVA_WORKSPACE_ID format. Must be a valid UUID.",
        )

    # Query for existing external identity
    external_identity = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.workspace_id == workspace_uuid,
            ExternalIdentity.external_user_id == x_user_id,
        )
        .first()
    )

    if not external_identity:
        # Create new external identity record
        external_identity = ExternalIdentity(
            workspace_id=workspace_uuid,
            external_user_id=x_user_id,
        )
        db.add(external_identity)
        db.flush()

    return ExternalPrincipal(
        workspace_id=settings.MINERVA_WORKSPACE_ID,
        external_user_id=x_user_id,
        is_guest=False,
        is_active=True,
    )
