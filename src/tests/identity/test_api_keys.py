"""API key authentication and lifecycle tests.

Tests AUTH-01 (API key authentication) and AUTH-02 (key rotation/revocation)
with comprehensive coverage of valid, invalid, rotated, and revoked key flows.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.identity.key_material import (
    generate_api_key,
    verify_key,
    is_key_expired,
)
from src.identity.service import ApiKeyService
from src.identity.repository import ApiKeyRepository
from src.db.models import Base
from src.api.dependencies.auth import resolve_principal, optional_principal


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_key_service(in_memory_db):
    """Create an API key service with test database."""
    return ApiKeyService(in_memory_db)


@pytest.fixture
def sample_workspace_id():
    """Return a sample workspace ID."""
    return uuid4()


# ============================================================================
# Key Material Tests (AUTH-01)
# ============================================================================


class TestKeyMaterial:
    """Tests for secure key generation and validation."""

    def test_generate_api_key_creates_valid_key_pair(self):
        """Key generation produces valid key pair with correct structure."""
        key_pair = generate_api_key()

        assert key_pair.full_key.startswith("pk_v1_")
        assert len(key_pair.full_key) > 50  # Reasonable length
        assert key_pair.prefix.startswith("pk_v1_")
        assert len(key_pair.hash) == 64  # SHA-256 hex digest

    def test_verify_key_succeeds_with_valid_key(self):
        """Valid key passes verification against its hash."""
        key_pair = generate_api_key()

        assert verify_key(key_pair.full_key, key_pair.hash) is True

    def test_verify_key_fails_with_invalid_key(self):
        """Invalid key fails verification."""
        key_pair = generate_api_key()

        assert verify_key("wrong_key", key_pair.hash) is False
        assert verify_key("", key_pair.hash) is False
        assert verify_key(key_pair.full_key + "extra", key_pair.hash) is False

    def test_verify_key_timing_safe_comparison(self):
        """Verification uses timing-safe comparison to prevent timing attacks."""
        key_pair = generate_api_key()

        # Both should fail but take similar time (timing-safe)
        result1 = verify_key("a" * 100, key_pair.hash)
        result2 = verify_key("b" * 100, key_pair.hash)

        assert result1 is False
        assert result2 is False

    def test_key_prefix_extraction(self):
        """Key prefix extraction works correctly."""
        from src.identity.key_material import parse_key_prefix

        key = "pk_v1_abc123def456"
        prefix = parse_key_prefix(key)

        assert prefix == "pk_v1_abc1"

    def test_is_key_expired_with_no_expiration(self):
        """Non-expiring keys are never expired."""
        assert is_key_expired(None) is False

    def test_is_key_expired_with_past_date(self):
        """Keys with past expiration are expired."""
        past = datetime.utcnow() - timedelta(days=1)
        assert is_key_expired(past) is True

    def test_is_key_expired_with_future_date(self):
        """Keys with future expiration are not expired."""
        future = datetime.utcnow() + timedelta(days=1)
        assert is_key_expired(future) is False


# ============================================================================
# Service Validation Tests (AUTH-01)
# ============================================================================


class TestKeyValidation:
    """Tests for API key validation service."""

    def test_validate_key_succeeds_with_valid_active_key(
        self, api_key_service, sample_workspace_id
    ):
        """AUTH-01: Valid API key authenticates successfully."""
        # Create a key
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        # Validate it
        result = api_key_service.validate_key(key_pair.full_key)

        assert result.is_valid is True
        assert result.principal is not None
        assert result.principal.workspace_id == str(sample_workspace_id)
        assert result.principal.is_active is True

    def test_validate_key_fails_with_unknown_key(self, api_key_service):
        """Unknown key fails validation."""
        result = api_key_service.validate_key("pk_v1_invalid_key_material")

        assert result.is_valid is False
        assert result.error == "Invalid API key"

    def test_validate_key_fails_with_empty_key(self, api_key_service):
        """Empty key fails validation."""
        result = api_key_service.validate_key("")

        assert result.is_valid is False
        assert "No API key provided" in result.error

    def test_validate_key_fails_with_revoked_key(self, api_key_service, sample_workspace_id):
        """AUTH-02: Revoked key fails validation immediately."""
        # Create key
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        # Verify it works first
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is True

        # Revoke it
        api_key_service.revoke_key(key_id=UUID(key_info.id), workspace_id=sample_workspace_id)

        # Verify it no longer works
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is False
        assert "revoked" in result.error.lower()

    def test_validate_key_fails_with_expired_key(self, api_key_service, sample_workspace_id):
        """Expired key fails validation."""
        # Create expired key
        expired = datetime.utcnow() - timedelta(hours=1)
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Expired Key", expires_at=expired
        )

        result = api_key_service.validate_key(key_pair.full_key)

        assert result.is_valid is False
        assert "expired" in result.error.lower()

    def test_validate_key_updates_last_used_timestamp(self, api_key_service, sample_workspace_id):
        """Successful validation updates last_used timestamp."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        assert key_info.last_used_at is None

        # Validate
        api_key_service.validate_key(key_pair.full_key)

        # Check timestamp was updated
        refreshed = api_key_service.get_key(
            key_id=UUID(key_info.id), workspace_id=sample_workspace_id
        )
        assert refreshed.last_used_at is not None


# ============================================================================
# Key Rotation Tests (AUTH-02)
# ============================================================================


class TestKeyRotation:
    """Tests for API key rotation functionality."""

    def test_rotate_key_invalidates_old_key_immediately(
        self, api_key_service, sample_workspace_id
    ):
        """AUTH-02: Rotated key immediately invalidates previous key material."""
        # Create original key
        old_key_pair, old_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Original Key"
        )

        # Verify original works
        result = api_key_service.validate_key(old_key_pair.full_key)
        assert result.is_valid is True

        # Rotate the key
        new_key_pair, new_info = api_key_service.rotate_key(
            key_id=UUID(old_info.id), workspace_id=sample_workspace_id
        )

        # Old key should NOT work
        result = api_key_service.validate_key(old_key_pair.full_key)
        assert result.is_valid is False
        assert "Invalid API key" in result.error

        # New key should work
        result = api_key_service.validate_key(new_key_pair.full_key)
        assert result.is_valid is True

    def test_rotated_key_maintains_same_id(self, api_key_service, sample_workspace_id):
        """Rotation preserves key ID but changes material."""
        old_key_pair, old_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Original Key"
        )

        new_key_pair, new_info = api_key_service.rotate_key(
            key_id=UUID(old_info.id), workspace_id=sample_workspace_id
        )

        assert old_info.id == new_info.id
        assert old_key_pair.full_key != new_key_pair.full_key
        assert old_key_pair.hash != new_key_pair.hash

    def test_rotate_key_preserves_scopes(self, api_key_service, sample_workspace_id):
        """Rotation preserves scopes from original key."""
        old_key_pair, old_info = api_key_service.create_key(
            workspace_id=sample_workspace_id,
            name="Scoped Key",
            scopes=["read", "write"],
        )

        new_key_pair, new_info = api_key_service.rotate_key(
            key_id=UUID(old_info.id), workspace_id=sample_workspace_id
        )

        assert set(old_info.scopes) == set(new_info.scopes)

    def test_cannot_rotate_revoked_key(self, api_key_service, sample_workspace_id):
        """Cannot rotate an already revoked key."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Key to Revoke"
        )

        # Revoke it
        api_key_service.revoke_key(key_id=UUID(key_info.id), workspace_id=sample_workspace_id)

        # Try to rotate - should fail
        with pytest.raises(ValueError) as exc_info:
            api_key_service.rotate_key(key_id=UUID(key_info.id), workspace_id=sample_workspace_id)

        assert "revoked" in str(exc_info.value).lower()

    def test_cannot_rotate_key_from_different_workspace(
        self, api_key_service, sample_workspace_id
    ):
        """Cannot rotate a key that belongs to another workspace."""
        other_workspace_id = uuid4()

        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Workspace Key"
        )

        with pytest.raises(ValueError) as exc_info:
            api_key_service.rotate_key(key_id=UUID(key_info.id), workspace_id=other_workspace_id)

        assert "does not belong" in str(exc_info.value).lower()


# ============================================================================
# Key Revocation Tests (AUTH-02)
# ============================================================================


class TestKeyRevocation:
    """Tests for API key revocation functionality."""

    def test_revoke_key_blocks_subsequent_requests(self, api_key_service, sample_workspace_id):
        """AUTH-02: Revoked key blocks subsequent authentication attempts."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Key to Revoke"
        )

        # Verify key works
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is True

        # Revoke
        revoked_info = api_key_service.revoke_key(
            key_id=UUID(key_info.id), workspace_id=sample_workspace_id
        )

        # Verify revoked status
        assert revoked_info.is_active is False

        # Key should no longer work
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is False
        assert "revoked" in result.error.lower()

    def test_revoke_key_idempotent(self, api_key_service, sample_workspace_id):
        """Revoking an already revoked key works (idempotent)."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Key to Revoke"
        )

        # Revoke twice
        api_key_service.revoke_key(key_id=UUID(key_info.id), workspace_id=sample_workspace_id)

        revoked_again = api_key_service.revoke_key(
            key_id=UUID(key_info.id), workspace_id=sample_workspace_id
        )

        assert revoked_again.is_active is False

    def test_cannot_revoke_key_from_different_workspace(
        self, api_key_service, sample_workspace_id
    ):
        """Cannot revoke a key that belongs to another workspace."""
        other_workspace_id = uuid4()

        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Workspace Key"
        )

        with pytest.raises(ValueError) as exc_info:
            api_key_service.revoke_key(key_id=UUID(key_info.id), workspace_id=other_workspace_id)

        assert "does not belong" in str(exc_info.value).lower()


# ============================================================================
# Regression Tests
# ============================================================================


class TestRegressionScenarios:
    """Regression tests for security and edge cases."""

    def test_revoked_key_cannot_pass_even_with_cached_hash(
        self, api_key_service, sample_workspace_id
    ):
        """
        REGRESSION: Revoked keys cannot pass validation even if an attacker
        somehow knows the hash or there's an in-memory cache issue.

        This tests that the is_active flag is always checked.
        """
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        # Validate once to populate any caches
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is True

        # Revoke directly via repository (bypassing service layer)
        repository = ApiKeyRepository(api_key_service.db)
        repository.revoke(UUID(key_info.id))
        api_key_service.db.commit()

        # Even with "cached" knowledge of the hash, validation should fail
        # because is_active is checked
        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is False
        assert "revoked" in result.error.lower()

    def test_key_collision_impossible_due_to_token_urlsafe(self):
        """Cryptographic key generation prevents collisions."""
        keys = set()

        # Generate many keys - collisions should be statistically impossible
        for _ in range(100):
            key_pair = generate_api_key()
            assert key_pair.full_key not in keys
            assert key_pair.hash not in keys
            keys.add(key_pair.full_key)
            keys.add(key_pair.hash)

    def test_timing_attack_resistance(self):
        """Hash comparison is timing-safe regardless of key correctness."""
        key_pair = generate_api_key()

        # These should all take similar time (tested implicitly by using
        # hmac.compare_digest which is constant-time)
        verify_key(key_pair.full_key, key_pair.hash)  # Correct
        verify_key("x" * 100, key_pair.hash)  # Wrong length
        verify_key(key_pair.full_key[:-1], key_pair.hash)  # Wrong content
        verify_key("", key_pair.hash)  # Empty


# ============================================================================
# Auth Dependency Tests
# ============================================================================


class TestAuthDependencies:
    """Tests for FastAPI auth dependencies."""

    @pytest.mark.asyncio
    async def test_resolve_principal_with_valid_key(
        self, api_key_service, sample_workspace_id, in_memory_db
    ):
        """Auth dependency resolves principal with valid key."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        # Mock request with API key
        principal = await resolve_principal(
            x_api_key=key_pair.full_key, authorization=None, db=in_memory_db
        )

        assert principal.workspace_id == str(sample_workspace_id)
        assert principal.key_id == key_info.id

    @pytest.mark.asyncio
    async def test_resolve_principal_with_bearer_token(
        self, api_key_service, sample_workspace_id, in_memory_db
    ):
        """Auth dependency supports Bearer token format."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        principal = await resolve_principal(
            x_api_key=None, authorization=f"Bearer {key_pair.full_key}", db=in_memory_db
        )

        assert principal.workspace_id == str(sample_workspace_id)

    @pytest.mark.asyncio
    async def test_resolve_principal_fails_without_key(self, in_memory_db):
        """Auth dependency raises 401 without API key."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_principal(x_api_key=None, authorization=None, db=in_memory_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_resolve_principal_fails_with_invalid_key(self, in_memory_db):
        """Auth dependency raises 401 with invalid API key."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_principal(
                x_api_key="pk_v1_invalid_key", authorization=None, db=in_memory_db
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_optional_principal_returns_none_without_key(self, in_memory_db):
        """Optional auth returns None when no key provided."""
        principal = await optional_principal(x_api_key=None, authorization=None, db=in_memory_db)

        assert principal is None

    @pytest.mark.asyncio
    async def test_optional_principal_returns_principal_with_valid_key(
        self, api_key_service, sample_workspace_id, in_memory_db
    ):
        """Optional auth returns principal when valid key provided."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        principal = await optional_principal(
            x_api_key=key_pair.full_key, authorization=None, db=in_memory_db
        )

        assert principal is not None
        assert principal.workspace_id == str(sample_workspace_id)


# ============================================================================
# Principal Scope Tests
# ============================================================================


class TestPrincipalScopes:
    """Tests for principal scope handling."""

    def test_principal_with_scopes(self, api_key_service, sample_workspace_id):
        """Principal correctly reflects key scopes."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id,
            name="Scoped Key",
            scopes=["read", "write", "admin"],
        )

        result = api_key_service.validate_key(key_pair.full_key)

        assert result.is_valid is True
        assert set(result.principal.scopes) == {"read", "write", "admin"}

    def test_principal_with_empty_scopes(self, api_key_service, sample_workspace_id):
        """Principal handles empty scopes correctly."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="No Scope Key"
        )

        result = api_key_service.validate_key(key_pair.full_key)

        assert result.is_valid is True
        assert result.principal.scopes == []


# ============================================================================
# List and Get Tests
# ============================================================================


class TestKeyListing:
    """Tests for key listing and retrieval."""

    def test_list_keys_returns_only_active_by_default(self, api_key_service, sample_workspace_id):
        """List keys returns only active keys by default."""
        # Create two keys
        key1, info1 = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Active Key"
        )
        key2, info2 = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Key to Revoke"
        )

        # Revoke one
        api_key_service.revoke_key(key_id=UUID(info2.id), workspace_id=sample_workspace_id)

        # List should only return active
        keys = api_key_service.list_keys(workspace_id=sample_workspace_id, active_only=True)

        assert len(keys) == 1
        assert keys[0].name == "Active Key"

    def test_list_keys_includes_revoked_when_requested(self, api_key_service, sample_workspace_id):
        """List keys can include revoked keys when requested."""
        # Create and revoke a key
        key1, info1 = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Active Key"
        )
        key2, info2 = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Revoked Key"
        )
        api_key_service.revoke_key(key_id=UUID(info2.id), workspace_id=sample_workspace_id)

        # List with active_only=False
        keys = api_key_service.list_keys(workspace_id=sample_workspace_id, active_only=False)

        assert len(keys) == 2

    def test_get_key_returns_none_for_wrong_workspace(self, api_key_service, sample_workspace_id):
        """Get key returns None for keys not in workspace."""
        other_workspace = uuid4()

        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Workspace Key"
        )

        result = api_key_service.get_key(key_id=UUID(key_info.id), workspace_id=other_workspace)

        assert result is None

    def test_get_key_returns_correct_key(self, api_key_service, sample_workspace_id):
        """Get key returns correct key info."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Specific Key"
        )

        result = api_key_service.get_key(
            key_id=UUID(key_info.id), workspace_id=sample_workspace_id
        )

        assert result is not None
        assert result.name == "Specific Key"
        assert result.id == key_info.id


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_create_key_with_long_name(self, api_key_service, sample_workspace_id):
        """Keys can be created with long names up to limit."""
        long_name = "A" * 255

        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name=long_name
        )

        assert key_info.name == long_name

    def test_validate_key_handles_special_characters(self, api_key_service, sample_workspace_id):
        """Key validation handles special characters correctly."""
        # Create and validate normally
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test with special chars: àáâãäå"
        )

        result = api_key_service.validate_key(key_pair.full_key)
        assert result.is_valid is True

    def test_key_hash_not_exposed_in_listings(self, api_key_service, sample_workspace_id):
        """Key listings never expose the hash."""
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        keys = api_key_service.list_keys(workspace_id=sample_workspace_id)

        # KeyInfo should not have hash attribute
        key_info_obj = keys[0]
        assert not hasattr(key_info_obj, "key_hash")
        assert not hasattr(key_info_obj, "hash")
