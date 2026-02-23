"""API Key service for authentication and lifecycle management.

Provides high-level operations for API key creation, rotation,
revocation, and validation with proper security semantics.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from src.identity.key_material import (
    generate_api_key,
    verify_key,
    KeyPair,
    Principal,
    is_key_expired,
)
from src.identity.repository import ApiKeyRepository
from src.db.models import ApiKey


@dataclass
class ValidationResult:
    """Result of API key validation."""

    is_valid: bool
    principal: Optional[Principal] = None
    error: Optional[str] = None


@dataclass
class KeyInfo:
    """Public information about an API key (without sensitive data)."""

    id: str
    workspace_id: str
    user_id: str
    name: str
    prefix: str
    scopes: List[str]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime


class ApiKeyService:
    """Service for API key lifecycle and validation."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ApiKeyRepository(db)

    def create_key(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> tuple[KeyPair, KeyInfo]:
        """Create a new API key for a workspace.

        Args:
            workspace_id: The workspace this key belongs to
            user_id: The user who owns this key
            name: Human-readable name for the key
            scopes: List of permission scopes (optional)
            expires_at: Optional expiration timestamp

        Returns:
            Tuple of (KeyPair with full key to show user, KeyInfo metadata)

        Raises:
            ValueError: If workspace_id is invalid
        """
        # Generate secure key material
        key_pair = generate_api_key(prefix="pk", key_length=48, version="v1")

        # Convert scopes list to comma-separated string for storage
        scopes_str = ",".join(scopes) if scopes else None

        # Persist to database (only hash, never the full key)
        api_key = self.repository.create(
            workspace_id=workspace_id,
            user_id=user_id,
            name=name,
            key_hash=key_pair.hash,
            key_prefix=key_pair.prefix,
            scopes=scopes_str,
            expires_at=expires_at,
        )

        self.db.commit()

        key_info = self._to_key_info(api_key)
        return key_pair, key_info

    def validate_key(self, provided_key: str) -> ValidationResult:
        """Validate an API key and return the associated principal.

        This method performs timing-safe hash comparison and checks
        key status (active, not expired, not revoked).

        Args:
            provided_key: The API key from the request header

        Returns:
            ValidationResult with is_valid flag and principal/error info
        """
        if not provided_key:
            return ValidationResult(is_valid=False, error="No API key provided")

        # Compute hash to look up (we don't store full keys)
        from src.identity.key_material import _hash_key

        key_hash = _hash_key(provided_key)

        # Find key by hash
        api_key = self.repository.get_by_hash(key_hash)

        if api_key is None:
            return ValidationResult(is_valid=False, error="Invalid API key")

        # Double-check with timing-safe comparison
        if not verify_key(provided_key, api_key.key_hash):
            return ValidationResult(is_valid=False, error="Invalid API key")

        # Check if key is active
        if not api_key.is_active:
            return ValidationResult(is_valid=False, error="API key has been revoked")

        # Check if key has expired
        if is_key_expired(api_key.expires_at):
            return ValidationResult(is_valid=False, error="API key has expired")

        # Update last_used timestamp (fire and forget, don't fail auth if this errors)
        try:
            self.repository.update_last_used(api_key.id)
            self.db.commit()
        except Exception:
            self.db.rollback()

        # Parse scopes
        scopes = []
        if api_key.scopes:
            scopes = [s.strip() for s in api_key.scopes.split(",") if s.strip()]

        # Build principal
        principal = Principal(
            workspace_id=str(api_key.workspace_id),
            key_id=str(api_key.id),
            user_id=str(api_key.user_id),
            scopes=scopes,
            is_active=api_key.is_active,
        )

        return ValidationResult(is_valid=True, principal=principal)

    def rotate_key(self, key_id: UUID, workspace_id: UUID) -> tuple[KeyPair, KeyInfo]:
        """Rotate an API key, invalidating the old key material.

        Rotation immediately invalidates the previous key. The new key
        maintains the same workspace association and scopes.

        Args:
            key_id: The ID of the key to rotate
            workspace_id: The workspace (for authorization check)

        Returns:
            Tuple of (KeyPair with new full key, KeyInfo metadata)

        Raises:
            ValueError: If key not found or doesn't belong to workspace
        """
        # Get existing key
        existing = self.repository.get_by_id(key_id)
        if existing is None:
            raise ValueError(f"API key not found: {key_id}")

        if existing.workspace_id != workspace_id:
            raise ValueError("API key does not belong to this workspace")

        if not existing.is_active:
            raise ValueError("Cannot rotate a revoked key")

        # Generate new key material
        new_key_pair = generate_api_key(prefix="pk", key_length=48, version="v1")

        # Update key material (invalidates old key immediately)
        updated = self.repository.update_key_material(
            key_id=key_id, new_hash=new_key_pair.hash, new_prefix=new_key_pair.prefix
        )

        if updated is None:
            raise ValueError(f"Failed to rotate key: {key_id}")

        self.db.commit()

        key_info = self._to_key_info(updated)
        return new_key_pair, key_info

    def revoke_key(self, key_id: UUID, workspace_id: UUID) -> KeyInfo:
        """Revoke an API key, preventing further use.

        Revoked keys cannot be used for authentication. This is
        typically used when a key is compromised or no longer needed.

        Args:
            key_id: The ID of the key to revoke
            workspace_id: The workspace (for authorization check)

        Returns:
            KeyInfo of the revoked key

        Raises:
            ValueError: If key not found or doesn't belong to workspace
        """
        # Get existing key
        existing = self.repository.get_by_id(key_id)
        if existing is None:
            raise ValueError(f"API key not found: {key_id}")

        if existing.workspace_id != workspace_id:
            raise ValueError("API key does not belong to this workspace")

        # Revoke the key
        revoked = self.repository.revoke(key_id)
        if revoked is None:
            raise ValueError(f"Failed to revoke key: {key_id}")

        self.db.commit()

        return self._to_key_info(revoked)

    def list_keys(self, workspace_id: UUID, active_only: bool = True) -> List[KeyInfo]:
        """List API keys for a workspace.

        Args:
            workspace_id: The workspace to list keys for
            active_only: If True, only return active keys

        Returns:
            List of key info objects (without sensitive hash data)
        """
        keys = self.repository.get_by_workspace(workspace_id, active_only)
        return [self._to_key_info(k) for k in keys]

    def get_key(self, key_id: UUID, workspace_id: UUID) -> Optional[KeyInfo]:
        """Get a specific API key by ID.

        Args:
            key_id: The key ID
            workspace_id: The workspace (for authorization check)

        Returns:
            KeyInfo if found and belongs to workspace, None otherwise
        """
        key = self.repository.get_by_id(key_id)
        if key is None or key.workspace_id != workspace_id:
            return None
        return self._to_key_info(key)

    def _to_key_info(self, api_key: ApiKey) -> KeyInfo:
        """Convert ApiKey model to KeyInfo DTO."""
        scopes = []
        if api_key.scopes:
            scopes = [s.strip() for s in api_key.scopes.split(",") if s.strip()]

        return KeyInfo(
            id=str(api_key.id),
            workspace_id=str(api_key.workspace_id),
            user_id=str(api_key.user_id),
            name=api_key.name,
            prefix=api_key.key_prefix,
            scopes=scopes,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
        )
