"""Integration test fixtures for Phase 1 acceptance testing.

Provides reusable fixtures for owner/member/guest principals, workspaces,
active/revoked keys, and run policy contexts. All fixtures are deterministic
and use isolated database state for reliable integration testing.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID
from typing import Dict, Any, List, Generator, Tuple
from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from src.main import app
from src.db.session import get_db, Base
from src.db.models import User, Workspace, Membership, ApiKey, WorkspaceResource
from src.identity.key_material import generate_api_key, KeyPair
from src.identity.service import ApiKeyService
from src.identity.key_material import Principal
from src.guest.identity import GuestPrincipal, create_guest_principal
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def db_engine(tmp_path):
    """Create a file-based SQLite database engine for tests.

    File-based is necessary because in-memory SQLite doesn't share
    connections between the test fixtures and the test client.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()

    # Enable foreign key support for SQLite
    session.execute(text("PRAGMA foreign_keys=ON"))
    session.commit()

    yield session

    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(db_engine) -> Generator[TestClient, None, None]:
    """Create a test client with database override using shared engine."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# User and Workspace Fixtures
# ============================================================================


@pytest.fixture
def workspace_owner(db_session: Session) -> User:
    """Create a workspace owner user."""
    user = User(
        id=uuid4(),
        email="owner@example.com",
        is_active=True,
        is_guest=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def workspace_member(db_session: Session) -> User:
    """Create a workspace member user."""
    user = User(
        id=uuid4(),
        email="member@example.com",
        is_active=True,
        is_guest=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def guest_user() -> GuestPrincipal:
    """Create a guest principal."""
    return create_guest_principal()


@pytest.fixture
def workspace_alpha(db_session: Session, workspace_owner: User) -> Workspace:
    """Create workspace alpha owned by workspace_owner."""
    workspace = Workspace(
        id=uuid4(),
        name="Alpha Workspace",
        slug="alpha-workspace",
        owner_id=workspace_owner.id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def workspace_beta(db_session: Session, workspace_owner: User) -> Workspace:
    """Create workspace beta owned by workspace_owner."""
    workspace = Workspace(
        id=uuid4(),
        name="Beta Workspace",
        slug="beta-workspace",
        owner_id=workspace_owner.id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def owner_membership(
    db_session: Session, workspace_owner: User, workspace_alpha: Workspace
) -> Membership:
    """Create owner membership for workspace_alpha."""
    membership = Membership(
        id=uuid4(),
        user_id=workspace_owner.id,
        workspace_id=workspace_alpha.id,
        role="owner",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(membership)
    db_session.commit()
    return membership


@pytest.fixture
def member_membership(
    db_session: Session, workspace_member: User, workspace_alpha: Workspace
) -> Membership:
    """Create member membership for workspace_alpha."""
    membership = Membership(
        id=uuid4(),
        user_id=workspace_member.id,
        workspace_id=workspace_alpha.id,
        role="member",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(membership)
    db_session.commit()
    return membership


# ============================================================================
# API Key Fixtures
# ============================================================================


@pytest.fixture
def owner_api_key(
    db_session: Session, workspace_alpha: Workspace, workspace_owner: User
) -> Tuple[KeyPair, Any]:
    """Create an active API key for workspace_alpha (owner context)."""
    service = ApiKeyService(db_session)
    key_pair, key_info = service.create_key(
        workspace_id=workspace_alpha.id,
        user_id=workspace_owner.id,
        name="Owner Test Key",
        scopes=["workspace:read", "workspace:write"],
    )
    return key_pair, key_info


@pytest.fixture
def member_api_key(
    db_session: Session, workspace_alpha: Workspace, workspace_member: User
) -> Tuple[KeyPair, Any]:
    """Create an active API key for workspace_alpha (member context)."""
    service = ApiKeyService(db_session)
    key_pair, key_info = service.create_key(
        workspace_id=workspace_alpha.id,
        user_id=workspace_member.id,
        name="Member Test Key",
        scopes=["workspace:read"],
    )
    return key_pair, key_info


@pytest.fixture
def revoked_api_key(
    db_session: Session, workspace_alpha: Workspace, workspace_owner: User
) -> Tuple[KeyPair, Any]:
    """Create a revoked API key for workspace_alpha."""
    service = ApiKeyService(db_session)
    key_pair, key_info = service.create_key(
        workspace_id=workspace_alpha.id,
        user_id=workspace_owner.id,
        name="Revoked Test Key",
        scopes=["workspace:read"],
    )
    # Revoke the key
    service.revoke_key(key_id=UUID(key_info.id), workspace_id=workspace_alpha.id)
    return key_pair, key_info


@pytest.fixture
def other_workspace_key(
    db_session: Session, workspace_beta: Workspace, workspace_owner: User
) -> Tuple[KeyPair, Any]:
    """Create an API key for a different workspace (for isolation tests)."""
    service = ApiKeyService(db_session)
    key_pair, key_info = service.create_key(
        workspace_id=workspace_beta.id,
        user_id=workspace_owner.id,
        name="Other Workspace Key",
        scopes=["workspace:read", "workspace:write"],
    )
    return key_pair, key_info


@pytest.fixture
def expired_api_key(
    db_session: Session, workspace_alpha: Workspace, workspace_owner: User
) -> Tuple[KeyPair, Any]:
    """Create an expired API key for testing."""
    service = ApiKeyService(db_session)
    key_pair, key_info = service.create_key(
        workspace_id=workspace_alpha.id,
        user_id=workspace_owner.id,
        name="Expired Test Key",
        scopes=["workspace:read"],
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
    )
    return key_pair, key_info


# ============================================================================
# Principal Fixtures
# ============================================================================


@pytest.fixture
def owner_principal(owner_api_key: Tuple[KeyPair, Any]) -> Principal:
    """Create an owner principal from the owner API key."""
    _, key_info = owner_api_key
    return Principal(
        workspace_id=key_info.workspace_id,
        key_id=key_info.id,
        user_id=key_info.user_id,
        scopes=key_info.scopes,
        is_active=key_info.is_active,
    )


@pytest.fixture
def member_principal(member_api_key: Tuple[KeyPair, Any]) -> Principal:
    """Create a member principal from the member API key."""
    _, key_info = member_api_key
    return Principal(
        workspace_id=key_info.workspace_id,
        key_id=key_info.id,
        user_id=key_info.user_id,
        scopes=key_info.scopes,
        is_active=key_info.is_active,
    )


# ============================================================================
# Workspace Resource Fixtures
# ============================================================================


@pytest.fixture
def sample_resource(
    db_session: Session, workspace_alpha: Workspace
) -> WorkspaceResource:
    """Create a sample workspace resource."""
    resource = WorkspaceResource(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        resource_type="agent_config",
        name="Sample Agent",
        config='{"model": "gpt-4"}',
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(resource)
    db_session.commit()
    return resource


# ============================================================================
# Runtime Policy Fixtures
# ============================================================================


@pytest.fixture
def allow_all_policy() -> Dict[str, Any]:
    """Create a policy that allows all egress, tools, and secrets."""
    return {
        "allowed_hosts": ["*"],
        "allowed_tools": ["*"],
        "allowed_secrets": ["*"],
    }


@pytest.fixture
def deny_all_policy() -> Dict[str, Any]:
    """Create a policy that denies all egress, tools, and secrets."""
    return {
        "allowed_hosts": [],
        "allowed_tools": [],
        "allowed_secrets": [],
    }


@pytest.fixture
def restricted_egress_policy() -> Dict[str, Any]:
    """Create a policy that only allows specific hosts."""
    return {
        "allowed_hosts": ["api.example.com", "*.trusted.com"],
        "allowed_tools": ["read_file", "write_file"],
        "allowed_secrets": ["API_KEY", "DB_URL"],
    }


@pytest.fixture
def egress_policy_allow_all() -> EgressPolicy:
    """Egress policy allowing all hosts."""
    return EgressPolicy(allowed_hosts=["*"])


@pytest.fixture
def egress_policy_deny_all() -> EgressPolicy:
    """Egress policy denying all hosts."""
    return EgressPolicy(allowed_hosts=[])


@pytest.fixture
def egress_policy_restricted() -> EgressPolicy:
    """Egress policy with specific allowed hosts."""
    return EgressPolicy(allowed_hosts=["api.example.com", "*.trusted.com"])


@pytest.fixture
def tool_policy_allow_all() -> ToolPolicy:
    """Tool policy allowing all tools."""
    return ToolPolicy(allowed_tools=["*"])


@pytest.fixture
def tool_policy_deny_all() -> ToolPolicy:
    """Tool policy denying all tools."""
    return ToolPolicy(allowed_tools=[])


@pytest.fixture
def tool_policy_restricted() -> ToolPolicy:
    """Tool policy with specific allowed tools."""
    return ToolPolicy(allowed_tools=["read_file", "write_file", "http_get"])


@pytest.fixture
def secret_scope_allow_all() -> SecretScope:
    """Secret scope allowing all secrets."""
    return SecretScope(allowed_secrets=["*"])


@pytest.fixture
def secret_scope_deny_all() -> SecretScope:
    """Secret scope denying all secrets."""
    return SecretScope(allowed_secrets=[])


@pytest.fixture
def secret_scope_restricted() -> SecretScope:
    """Secret scope with specific allowed secrets."""
    return SecretScope(allowed_secrets=["API_KEY", "DB_URL", "TOKEN"])


# ============================================================================
# Helper Functions
# ============================================================================


def auth_headers(api_key: str) -> Dict[str, str]:
    """Create authorization headers for an API key."""
    return {"X-Api-Key": api_key}


def bearer_headers(api_key: str) -> Dict[str, str]:
    """Create Bearer authorization headers for an API key."""
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def owner_headers(owner_api_key: Tuple[KeyPair, Any]) -> Dict[str, str]:
    """Authorization headers for owner API key."""
    key_pair, _ = owner_api_key
    return auth_headers(key_pair.full_key)


@pytest.fixture
def member_headers(member_api_key: Tuple[KeyPair, Any]) -> Dict[str, str]:
    """Authorization headers for member API key."""
    key_pair, _ = member_api_key
    return auth_headers(key_pair.full_key)


@pytest.fixture
def revoked_headers(revoked_api_key: Tuple[KeyPair, Any]) -> Dict[str, str]:
    """Authorization headers for revoked API key."""
    key_pair, _ = revoked_api_key
    return auth_headers(key_pair.full_key)


@pytest.fixture
def other_workspace_headers(other_workspace_key: Tuple[KeyPair, Any]) -> Dict[str, str]:
    """Authorization headers for other workspace API key."""
    key_pair, _ = other_workspace_key
    return auth_headers(key_pair.full_key)


# Need to import Any for type hints
from typing import Any
