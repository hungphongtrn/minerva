"""Authentication dependencies for FastAPI routes.

Provides dependencies for resolving API keys to principals
and enforcing authentication on protected routes.
"""

from typing import Union

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.identity.service import ApiKeyService, ValidationResult, Principal
from src.guest.identity import create_guest_principal, GuestPrincipal

# Security scheme for OpenAPI documentation
security = HTTPBearer(auto_error=False)

# Type alias for any principal (authenticated or guest)
AnyPrincipal = Union[Principal, GuestPrincipal]


async def resolve_principal(
    x_api_key: str = Header(None, alias="X-Api-Key"),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> Principal:
    """Resolve an API key to an authenticated principal.

    This dependency validates the API key and returns the associated
    principal (workspace, scopes, etc.). It supports two header formats:
    - X-Api-Key: Direct API key header
    - Authorization: Bearer token format (Bearer <key>)

    Args:
        x_api_key: API key from X-Api-Key header
        authorization: API key from Authorization header (Bearer format)
        db: Database session

    Returns:
        Principal containing workspace_id, key_id, scopes, is_active

    Raises:
        HTTPException: 401 if key is invalid, revoked, expired, or missing
    """
    # Extract key from header
    api_key = None

    if x_api_key:
        api_key = x_api_key
    elif authorization:
        # Support Bearer token format: "Bearer <token>"
        if authorization.lower().startswith("bearer "):
            api_key = authorization[7:]  # Remove "Bearer " prefix
        else:
            api_key = authorization

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-Api-Key header or Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the key
    service = ApiKeyService(db)
    result: ValidationResult = service.validate_key(api_key)

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result.principal


async def optional_principal(
    x_api_key: str = Header(None, alias="X-Api-Key"),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> Principal | None:
    """Optionally resolve an API key to a principal.

    Similar to resolve_principal but returns None instead of raising
    an exception when no key is provided. Useful for endpoints that
    support both authenticated and guest access.

    Args:
        x_api_key: API key from X-Api-Key header
        authorization: API key from Authorization header (Bearer format)
        db: Database session

    Returns:
        Principal if key is valid, None otherwise
    """
    # Extract key from header
    api_key = None

    if x_api_key:
        api_key = x_api_key
    elif authorization:
        if authorization.lower().startswith("bearer "):
            api_key = authorization[7:]
        else:
            api_key = authorization

    if not api_key:
        return None

    # Validate the key
    service = ApiKeyService(db)
    result: ValidationResult = service.validate_key(api_key)

    if not result.is_valid:
        # For optional auth, we return None rather than raising
        return None

    return result.principal


class require_scopes:
    """Dependency factory to require specific scopes.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            principal: Principal = Depends(require_scopes(["admin"]))
        ):
            ...
    """

    def __init__(self, required_scopes: list[str]):
        self.required_scopes = set(required_scopes)

    def __call__(self, principal: Principal = Depends(resolve_principal)) -> Principal:
        """Check if principal has required scopes."""
        principal_scopes = set(principal.scopes)

        # Check for wildcard scope (grants all permissions)
        if "*" in principal_scopes:
            return principal

        # Check if all required scopes are present
        missing = self.required_scopes - principal_scopes
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Missing scopes: {', '.join(missing)}",
            )

        return principal


async def resolve_principal_or_guest(
    x_api_key: str = Header(None, alias="X-Api-Key"),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> AnyPrincipal:
    """Resolve an API key to a principal, or create a guest principal.

    This dependency validates the API key and returns the associated
    principal. If no key is provided, it creates an ephemeral guest
    principal instead of raising an error.

    Malformed or invalid provided keys still raise 401 errors - guest
    mode is only used when NO key is provided at all.

    Args:
        x_api_key: API key from X-Api-Key header
        authorization: API key from Authorization header (Bearer format)
        db: Database session

    Returns:
        Principal if key valid, GuestPrincipal if no key provided

    Raises:
        HTTPException: 401 if provided key is invalid, revoked, or expired
    """
    # Extract key from header
    api_key = None

    if x_api_key:
        api_key = x_api_key
    elif authorization:
        # Support Bearer token format: "Bearer <token>"
        if authorization.lower().startswith("bearer "):
            api_key = authorization[7:]  # Remove "Bearer " prefix
        else:
            api_key = authorization

    # No key provided - create guest principal
    if not api_key:
        return create_guest_principal()

    # Key provided - validate it (invalid keys still fail)
    service = ApiKeyService(db)
    result: ValidationResult = service.validate_key(api_key)

    if not result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result.principal


def require_non_guest():
    """Dependency factory to require authenticated (non-guest) access.

    Usage:
        @router.post("/runs")
        async def create_run(
            principal: AnyPrincipal = Depends(require_non_guest())
        ):
            # Only authenticated users reach here
            ...
    """

    async def _check(
        principal: AnyPrincipal = Depends(resolve_principal_or_guest),
    ) -> Principal:
        """Check that principal is not a guest."""
        if getattr(principal, "is_guest", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide a valid API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # At this point we know it's a real Principal
        return principal

    return _check
