"""External identity dependency for OSS gateway passthrough.

This module provides authentication for OSS end-user requests where the
developer's gateway handles authentication and passes the user ID via
the X-User-ID header. Minerva trusts this header as an opaque identifier.
"""

from typing import NamedTuple, Optional
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import User, Workspace


class ExternalPrincipal(NamedTuple):
    """Principal for OSS end-user requests via gateway passthrough.

    The gateway authenticates the end-user and sets X-User-ID header.
    Minerva treats this as an opaque string and manages workspace/sandbox
    lifecycle per user automatically.
    """

    user_id: str  # UUID string of the internal user record
    workspace_id: str  # UUID string of the user's workspace
    external_user_id: str  # The X-User-ID value from the gateway (opaque)
    is_active: bool = True


async def resolve_external_principal(
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: Session = Depends(get_db),
) -> ExternalPrincipal:
    """Resolve X-User-ID header to an external principal with workspace.

    This dependency:
    1. Requires X-User-ID header (returns 400 if missing)
    2. Gets or creates a User record keyed by users.email = X-User-ID
    3. Ensures a durable workspace exists for that user
    4. Returns ExternalPrincipal with workspace_id and user_id

    The X-User-ID is treated as an opaque string. No format validation
    is performed other than enforcing database length bounds (255 chars).
    No API keys are created - the gateway owns authentication entirely.

    Args:
        x_user_id: User ID from X-User-ID header (set by gateway)
        db: Database session

    Returns:
        ExternalPrincipal with user_id, workspace_id, external_user_id

    Raises:
        HTTPException: 400 if X-User-ID header is missing or too long
    """
    # Require X-User-ID header
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID header required. Gateway must authenticate user.",
        )

    # Enforce database length bounds (email column is VARCHAR(255))
    if len(x_user_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID exceeds maximum length of 255 characters.",
        )

    # Get or create user by treating X-User-ID as opaque email identifier
    user = db.query(User).filter(User.email == x_user_id).first()

    if not user:
        # Create new user with X-User-ID as email
        user = User(
            id=uuid4(),
            email=x_user_id,
            is_active=True,
            is_guest=False,
        )
        db.add(user)
        db.flush()  # Get user.id assigned

    # Ensure workspace exists for this user
    workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()

    if not workspace:
        # Create workspace for user using email-based slug
        slug_base = x_user_id.replace("@", "-").replace(".", "-")
        # Truncate if too long and ensure uniqueness
        slug = slug_base[:80]  # Leave room for suffix
        original_slug = slug
        counter = 1

        # Check for slug uniqueness
        while db.query(Workspace).filter(Workspace.slug == slug).first():
            suffix = f"-{counter}"
            slug = original_slug[:80 - len(suffix)] + suffix
            counter += 1

        workspace = Workspace(
            id=uuid4(),
            name=f"{x_user_id}'s Workspace",
            slug=slug,
            owner_id=user.id,
            is_active=True,
        )
        db.add(workspace)
        db.flush()

    return ExternalPrincipal(
        user_id=str(user.id),
        workspace_id=str(workspace.id),
        external_user_id=x_user_id,
        is_active=user.is_active,
    )
