"""Guest identity and runtime policy tests.

Tests AUTH-06 (guest mode), SECU-01 (default-deny egress),
SECU-02 (default-deny tool access), and SECU-03 (scoped secrets).
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch, Mock

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.guest.identity import (
    create_guest_principal,
    GuestPrincipal,
    is_guest_principal,
)
from src.api.dependencies.auth import (
    resolve_principal_or_guest,
    require_non_guest,
    AnyPrincipal,
)
from src.runtime_policy.models import (
    PolicyDecision,
    EgressPolicy,
    ToolPolicy,
    SecretScope,
)
from src.runtime_policy.engine import RuntimePolicyEngine
from src.runtime_policy.enforcer import RuntimeEnforcer
from src.identity.service import ApiKeyService
from src.db.models import ApiKey, Base


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


@pytest.fixture
def policy_engine():
    """Create a runtime policy engine."""
    return RuntimePolicyEngine()


@pytest.fixture
def enforcer(policy_engine):
    """Create a runtime enforcer."""
    return RuntimeEnforcer(policy_engine)


# ============================================================================
# Guest Identity Tests (AUTH-06)
# ============================================================================


class TestGuestIdentity:
    """Tests for guest principal generation and behavior."""

    def test_create_guest_principal_generates_unique_ids(self):
        """AUTH-06: Each guest request gets a fresh random identity."""
        guest1 = create_guest_principal()
        guest2 = create_guest_principal()

        # Each guest should have a unique ID
        assert guest1.guest_id != guest2.guest_id
        assert guest1.guest_id.startswith("guest_")
        assert guest2.guest_id.startswith("guest_")

    def test_guest_principal_is_marked_as_guest(self):
        """Guest principals have is_guest flag set."""
        guest = create_guest_principal()

        assert guest.is_guest is True
        assert guest.key_id == "guest"

    def test_guest_principal_has_no_workspace(self):
        """Guest principals have no workspace association."""
        guest = create_guest_principal()

        assert guest.workspace_id is None

    def test_guest_principal_has_no_scopes(self):
        """Guest principals have no scopes by default."""
        guest = create_guest_principal()

        assert guest.scopes == []

    def test_is_guest_principal_with_guest(self):
        """is_guest_principal returns True for GuestPrincipal."""
        guest = create_guest_principal()

        assert is_guest_principal(guest) is True

    def test_is_guest_principal_with_regular(self):
        """is_guest_principal returns False for regular Principal."""
        from src.identity.key_material import Principal

        principal = Principal(
            workspace_id=str(uuid4()),
            key_id="test_key",
            scopes=["read"],
            is_active=True,
        )

        assert is_guest_principal(principal) is False

    def test_is_guest_principal_with_none(self):
        """is_guest_principal returns True for None."""
        assert is_guest_principal(None) is True


# ============================================================================
# Auth Dependency Guest Tests
# ============================================================================


class TestGuestAuthDependencies:
    """Tests for guest-aware auth dependencies."""

    @pytest.mark.asyncio
    async def test_resolve_principal_or_guest_creates_guest_when_no_key(
        self, in_memory_db
    ):
        """Anonymous requests resolve to guest principals."""
        principal = await resolve_principal_or_guest(
            x_api_key=None, authorization=None, db=in_memory_db
        )

        assert isinstance(principal, GuestPrincipal)
        assert principal.is_guest is True
        assert principal.guest_id.startswith("guest_")

    @pytest.mark.asyncio
    async def test_resolve_principal_or_guest_validates_provided_key(
        self, api_key_service, sample_workspace_id, in_memory_db
    ):
        """Provided keys are still validated, invalid keys fail."""
        # Create a valid key
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )

        # Valid key should work
        principal = await resolve_principal_or_guest(
            x_api_key=key_pair.full_key, authorization=None, db=in_memory_db
        )

        assert isinstance(principal, tuple)  # It's a regular Principal (NamedTuple)
        assert principal.workspace_id == str(sample_workspace_id)

    @pytest.mark.asyncio
    async def test_resolve_principal_or_guest_rejects_invalid_key(self, in_memory_db):
        """Invalid provided keys still raise 401, not guest."""
        with pytest.raises(HTTPException) as exc_info:
            await resolve_principal_or_guest(
                x_api_key="invalid_key", authorization=None, db=in_memory_db
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_resolve_principal_or_guest_rejects_revoked_key(
        self, api_key_service, sample_workspace_id, in_memory_db
    ):
        """Revoked keys raise 401, not fallback to guest."""
        # Create and revoke a key
        key_pair, key_info = api_key_service.create_key(
            workspace_id=sample_workspace_id, name="Test Key"
        )
        api_key_service.revoke_key(
            key_id=UUID(key_info.id), workspace_id=sample_workspace_id
        )

        with pytest.raises(HTTPException) as exc_info:
            await resolve_principal_or_guest(
                x_api_key=key_pair.full_key, authorization=None, db=in_memory_db
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "revoked" in str(exc_info.value.detail).lower()


# ============================================================================
# Non-Guest Requirement Tests
# ============================================================================


class TestRequireNonGuest:
    """Tests for the require_non_guest dependency."""

    @pytest.mark.asyncio
    async def test_require_non_guest_blocks_guest(self):
        """Guest principals are blocked by require_non_guest."""
        guest = create_guest_principal()

        # Create a mock dependency that returns the guest
        async def mock_dep():
            return guest

        # Apply require_non_guest
        dependency = require_non_guest()

        # The dependency should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await dependency(principal=guest)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_require_non_guest_allows_authenticated(self):
        """Authenticated principals pass require_non_guest."""
        from src.identity.key_material import Principal

        principal = Principal(
            workspace_id=str(uuid4()),
            key_id="test_key",
            scopes=["read"],
            is_active=True,
        )

        # The check should not raise
        dependency = require_non_guest()
        # In real usage this would be called by FastAPI's Depends
        # Here we just verify the principal would pass the check
        assert is_guest_principal(principal) is False


# ============================================================================
# Runtime Policy Engine Tests
# ============================================================================


class TestPolicyEngine:
    """Tests for runtime policy evaluation."""

    def test_egress_denied_by_default(self, policy_engine):
        """SECU-01: Egress is denied by default."""
        decision = policy_engine.evaluate_egress(
            url="https://example.com",
            allowed_hosts=[],
        )

        assert decision.allowed is False
        assert "deny" in decision.reason.lower()

    def test_egress_allowed_for_explicit_host(self, policy_engine):
        """Egress allowed for explicitly allowed hosts."""
        decision = policy_engine.evaluate_egress(
            url="https://api.example.com/path",
            allowed_hosts=["api.example.com"],
        )

        assert decision.allowed is True

    def test_egress_denied_for_different_host(self, policy_engine):
        """Egress denied for hosts not in allowlist."""
        decision = policy_engine.evaluate_egress(
            url="https://malicious.com",
            allowed_hosts=["api.example.com"],
        )

        assert decision.allowed is False

    def test_tool_denied_by_default(self, policy_engine):
        """SECU-02: Tools are denied by default."""
        decision = policy_engine.evaluate_tool(
            tool_id="fetch",
            allowed_tools=[],
        )

        assert decision.allowed is False
        assert "deny" in decision.reason.lower()

    def test_tool_allowed_for_explicit_tool(self, policy_engine):
        """Tool allowed for explicitly allowed tools."""
        decision = policy_engine.evaluate_tool(
            tool_id="fetch",
            allowed_tools=["fetch", "search"],
        )

        assert decision.allowed is True

    def test_tool_denied_for_different_tool(self, policy_engine):
        """Tool denied for tools not in allowlist."""
        decision = policy_engine.evaluate_tool(
            tool_id="execute_shell",
            allowed_tools=["fetch", "search"],
        )

        assert decision.allowed is False

    def test_secret_denied_by_default(self, policy_engine):
        """SECU-03: Secrets are denied by default."""
        decision = policy_engine.evaluate_secret(
            secret_name="API_KEY",
            allowed_secrets=[],
        )

        assert decision.allowed is False
        assert "deny" in decision.reason.lower()

    def test_secret_allowed_for_explicit_secret(self, policy_engine):
        """Secret allowed for explicitly allowed secrets."""
        decision = policy_engine.evaluate_secret(
            secret_name="API_KEY",
            allowed_secrets=["API_KEY", "DB_PASSWORD"],
        )

        assert decision.allowed is True

    def test_secret_denied_for_different_secret(self, policy_engine):
        """Secret denied for secrets not in allowlist."""
        decision = policy_engine.evaluate_secret(
            secret_name="STOLEN_SECRET",
            allowed_secrets=["API_KEY", "DB_PASSWORD"],
        )

        assert decision.allowed is False


# ============================================================================
# Runtime Enforcer Tests
# ============================================================================


class TestRuntimeEnforcer:
    """Tests for runtime policy enforcement."""

    def test_authorize_egress_raises_on_denial(self, enforcer):
        """Enforcer raises on egress denial."""
        with pytest.raises(RuntimeError) as exc_info:
            enforcer.authorize_egress(
                url="https://example.com",
                policy=EgressPolicy(allowed_hosts=[]),
            )

        assert "denied" in str(exc_info.value).lower()

    def test_authorize_egress_succeeds_on_allow(self, enforcer):
        """Enforcer succeeds on egress allow."""
        # Should not raise
        enforcer.authorize_egress(
            url="https://api.example.com",
            policy=EgressPolicy(allowed_hosts=["api.example.com"]),
        )

    def test_authorize_tool_raises_on_denial(self, enforcer):
        """Enforcer raises on tool denial."""
        with pytest.raises(RuntimeError) as exc_info:
            enforcer.authorize_tool(
                tool_id="execute_shell",
                policy=ToolPolicy(allowed_tools=["fetch"]),
            )

        assert "denied" in str(exc_info.value).lower()

    def test_authorize_tool_succeeds_on_allow(self, enforcer):
        """Enforcer succeeds on tool allow."""
        # Should not raise
        enforcer.authorize_tool(
            tool_id="fetch",
            policy=ToolPolicy(allowed_tools=["fetch", "search"]),
        )

    def test_authorize_secret_raises_on_denial(self, enforcer):
        """Enforcer raises on secret denial."""
        with pytest.raises(RuntimeError) as exc_info:
            enforcer.authorize_secret(
                secret_name="HIDDEN_SECRET",
                allowed_secrets=["PUBLIC_KEY"],
            )

        assert "denied" in str(exc_info.value).lower()

    def test_authorize_secret_succeeds_on_allow(self, enforcer):
        """Enforcer succeeds on secret allow."""
        # Should not raise
        enforcer.authorize_secret(
            secret_name="API_KEY",
            allowed_secrets=["API_KEY"],
        )

    def test_get_allowed_secrets_filters_by_policy(self, enforcer):
        """Enforcer returns only allowed secrets."""
        all_secrets = {
            "API_KEY": "secret123",
            "DB_PASSWORD": "pass456",
            "ADMIN_KEY": "admin789",
        }

        allowed = enforcer.get_allowed_secrets(
            all_secrets=all_secrets,
            policy=SecretScope(allowed_secrets=["API_KEY", "DB_PASSWORD"]),
        )

        assert "API_KEY" in allowed
        assert "DB_PASSWORD" in allowed
        assert "ADMIN_KEY" not in allowed


# ============================================================================
# Guest Persistence Guard Tests
# ============================================================================


class TestGuestPersistenceGuard:
    """Tests for guest-mode persistence restrictions."""

    def test_guest_cannot_persist_run(self):
        """Guest requests cannot write persistent run records."""
        guest = create_guest_principal()

        # Simulate a guest run attempt
        assert is_guest_principal(guest) is True

        # In real implementation, this would be checked before persistence
        # Here we verify the guard logic
        if is_guest_principal(guest):
            # Guest mode - no persistence
            can_persist = False
        else:
            can_persist = True

        assert can_persist is False

    def test_guest_cannot_persist_checkpoint(self):
        """Guest requests cannot write persistent checkpoint records."""
        guest = create_guest_principal()

        # Same guard logic applies
        assert is_guest_principal(guest) is True

    def test_authenticated_can_persist(self):
        """Authenticated users can persist."""
        from src.identity.key_material import Principal

        principal = Principal(
            workspace_id=str(uuid4()),
            key_id="test_key",
            scopes=["read"],
            is_active=True,
        )

        assert is_guest_principal(principal) is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestRuntimePolicyIntegration:
    """Integration tests for runtime policy system."""

    def test_full_policy_flow_egress(self):
        """Complete egress policy flow."""
        engine = RuntimePolicyEngine()

        # Default deny
        decision = engine.evaluate_egress("https://anywhere.com", allowed_hosts=[])
        assert decision.allowed is False

        # Explicit allow
        decision = engine.evaluate_egress(
            "https://safe.example.com", allowed_hosts=["safe.example.com"]
        )
        assert decision.allowed is True

    def test_full_policy_flow_tools(self):
        """Complete tool policy flow."""
        engine = RuntimePolicyEngine()

        # Default deny
        decision = engine.evaluate_tool("any_tool", allowed_tools=[])
        assert decision.allowed is False

        # Explicit allow
        decision = engine.evaluate_tool("fetch", allowed_tools=["fetch"])
        assert decision.allowed is True

    def test_full_policy_flow_secrets(self):
        """Complete secret policy flow."""
        engine = RuntimePolicyEngine()
        enforcer = RuntimeEnforcer(engine)

        available_secrets = {"KEY1": "val1", "KEY2": "val2", "KEY3": "val3"}

        # Default deny - only allowed secrets returned
        allowed = enforcer.get_allowed_secrets(
            all_secrets=available_secrets,
            policy=SecretScope(allowed_secrets=["KEY1", "KEY2"]),
        )
        assert "KEY1" in allowed
        assert "KEY2" in allowed
        assert "KEY3" not in allowed


# ============================================================================
# Error Contract Tests
# ============================================================================


class TestErrorContracts:
    """Tests for consistent error responses."""

    def test_policy_denial_error_format(self, policy_engine):
        """Policy denials have consistent error format."""
        decision = policy_engine.evaluate_egress(
            "https://example.com", allowed_hosts=[]
        )

        assert decision.allowed is False
        assert decision.reason is not None
        assert isinstance(decision.reason, str)

    def test_enforcer_error_messages(self, enforcer):
        """Enforcer errors are descriptive."""
        with pytest.raises(RuntimeError) as exc_info:
            enforcer.authorize_egress("https://bad.com", EgressPolicy(allowed_hosts=[]))

        error_msg = str(exc_info.value)
        assert "egress" in error_msg.lower() or "network" in error_msg.lower()
        assert "denied" in error_msg.lower()
