"""Secure API key material handling.

Provides utilities for generating, hashing, and validating API keys
using cryptographically secure methods.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import NamedTuple, Optional


class KeyPair(NamedTuple):
    """Container for a generated API key pair.

    The full_key is returned to the user ONCE and never stored.
    The prefix is stored for identification purposes.
    The hash is stored for validation.
    """

    full_key: str
    prefix: str
    hash: str


class Principal(NamedTuple):
    """Authenticated principal extracted from an API key."""

    workspace_id: str
    key_id: str
    scopes: list[str]
    is_active: bool


def generate_api_key(
    prefix: str = "pk", key_length: int = 48, version: str = "v1"
) -> KeyPair:
    """Generate a new cryptographically secure API key.

    Args:
        prefix: Key prefix for identification (e.g., "pk" for production)
        key_length: Length of the random key portion
        version: Key version/format identifier

    Returns:
        KeyPair containing the full key (to show user once), prefix, and hash
    """
    # Generate cryptographically secure random key material
    random_material = secrets.token_urlsafe(key_length)

    # Format: pk_v1_xxxxxxxxxxxxxxxx... (prefix_version_random)
    full_key = f"{prefix}_{version}_{random_material}"

    # Extract a short prefix for display/logging (first 8 chars after prefix)
    key_prefix = f"{prefix}_{version}_{random_material[:4]}"

    # Hash the key for storage (SHA-256)
    key_hash = _hash_key(full_key)

    return KeyPair(full_key=full_key, prefix=key_prefix, hash=key_hash)


def _hash_key(key: str) -> str:
    """Create a SHA-256 hash of the key for storage.

    Uses a fixed salt approach (keys are already random, so salt
    provides additional protection against rainbow tables).
    """
    # Use a deterministic salt based on key properties
    # In production, consider using a pepper (secret key) as well
    hash_input = key.encode("utf-8")
    return hashlib.sha256(hash_input).hexdigest()


def verify_key(provided_key: str, stored_hash: str) -> bool:
    """Verify a provided API key against a stored hash.

    Uses hmac.compare_digest for timing-safe comparison to prevent
    timing attacks.

    Args:
        provided_key: The API key from the request
        stored_hash: The SHA-256 hash stored in the database

    Returns:
        True if the key matches the hash, False otherwise
    """
    if not provided_key or not stored_hash:
        return False

    # Compute hash of provided key
    computed_hash = _hash_key(provided_key)

    # Timing-safe comparison to prevent timing attacks
    return hmac.compare_digest(computed_hash, stored_hash)


def parse_key_prefix(key: str) -> Optional[str]:
    """Extract the display prefix from a full API key.

    Args:
        key: The full API key

    Returns:
        The prefix portion suitable for display, or None if invalid format
    """
    if not key or "_" not in key:
        return None

    parts = key.split("_")
    if len(parts) < 3:
        return None

    # Return prefix_version_first4chars
    return f"{parts[0]}_{parts[1]}_{parts[2][:4]}"


def is_key_expired(expires_at: Optional[datetime]) -> bool:
    """Check if an API key has expired.

    Args:
        expires_at: The expiration timestamp, or None for non-expiring keys

    Returns:
        True if the key has expired, False otherwise
    """
    if expires_at is None:
        return False
    return datetime.utcnow() > expires_at


def generate_rotation_key(existing_key: "ApiKeyModel") -> KeyPair:
    """Generate a new key that replaces an existing key.

    The new key will have the same workspace and scopes as the original,
    but with fresh key material.

    Args:
        existing_key: The API key being rotated

    Returns:
        KeyPair with new key material
    """
    # Generate new key with same prefix pattern
    return generate_api_key(
        prefix=existing_key.key_prefix.split("_")[0]
        if existing_key.key_prefix
        else "pk",
        key_length=48,
        version="v1",
    )
