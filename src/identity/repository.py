"""API Key repository for database operations.

Provides CRUD operations for API keys with proper isolation
and security considerations.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, update

from src.db.models import ApiKey


class ApiKeyRepository:
    """Repository for API key persistence operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        """Get an API key by its hash.

        Args:
            key_hash: The SHA-256 hash of the key

        Returns:
            The API key if found and active, None otherwise
        """
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, key_id: UUID) -> Optional[ApiKey]:
        """Get an API key by its ID.

        Args:
            key_id: The UUID of the API key

        Returns:
            The API key if found, None otherwise
        """
        stmt = select(ApiKey).where(ApiKey.id == key_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_workspace(
        self, workspace_id: UUID, active_only: bool = True
    ) -> List[ApiKey]:
        """Get all API keys for a workspace.

        Args:
            workspace_id: The workspace UUID
            active_only: If True, only return active keys

        Returns:
            List of API keys
        """
        stmt = select(ApiKey).where(ApiKey.workspace_id == workspace_id)
        if active_only:
            stmt = stmt.where(ApiKey.is_active)
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> ApiKey:
        """Create a new API key.

        Args:
            workspace_id: The workspace this key belongs to
            user_id: The user who owns this key
            name: Human-readable name for the key
            key_hash: SHA-256 hash of the full key
            key_prefix: Display prefix (e.g., "pk_v1_abcd")
            scopes: Optional comma-separated scope list
            expires_at: Optional expiration timestamp

        Returns:
            The created API key
        """
        api_key = ApiKey(
            workspace_id=workspace_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            expires_at=expires_at,
            is_active=True,
        )
        self.db.add(api_key)
        self.db.flush()  # Get the ID without committing
        return api_key

    def update_key_material(
        self, key_id: UUID, new_hash: str, new_prefix: str
    ) -> Optional[ApiKey]:
        """Update the key material for rotation.

        This invalidates the old key material immediately.

        Args:
            key_id: The API key ID
            new_hash: The new key hash
            new_prefix: The new key prefix

        Returns:
            The updated API key, or None if not found
        """
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(
                key_hash=new_hash, key_prefix=new_prefix, updated_at=datetime.utcnow()
            )
            .returning(ApiKey)
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def revoke(self, key_id: UUID) -> Optional[ApiKey]:
        """Revoke an API key.

        Revoked keys cannot be used for authentication.

        Args:
            key_id: The API key ID

        Returns:
            The revoked API key, or None if not found
        """
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(is_active=False, updated_at=datetime.utcnow())
            .returning(ApiKey)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_last_used(self, key_id: UUID) -> None:
        """Update the last_used timestamp for a key.

        Args:
            key_id: The API key ID
        """
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(last_used_at=datetime.utcnow())
        )
        self.db.execute(stmt)

    def delete_permanently(self, key_id: UUID) -> bool:
        """Permanently delete an API key.

        Note: This is a hard delete. Prefer revoke() for normal operations.

        Args:
            key_id: The API key ID

        Returns:
            True if deleted, False if not found
        """
        key = self.get_by_id(key_id)
        if key:
            self.db.delete(key)
            return True
        return False
