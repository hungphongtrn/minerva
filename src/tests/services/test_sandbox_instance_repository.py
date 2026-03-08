"""Tests for sandbox instance repository.

Tests bridge token rotation with grace overlap, gateway URL authority,
identity readiness, checkpoint hydration state persistence, and
external_user_id persistence for per-user sandbox routing.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.db.models import (
    Base,
    User,
    Workspace,
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    SandboxHydrationStatus,
)
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email=f"test_{uuid4().hex[:8]}@example.com",
        is_active=True,
        is_guest=False,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_workspace(db_session: Session, test_user: User) -> Workspace:
    """Create a test workspace."""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug=f"test-workspace-{uuid4().hex[:8]}",
        owner_id=test_user.id,
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def repository(db_session: Session) -> SandboxInstanceRepository:
    """Create a sandbox instance repository."""
    return SandboxInstanceRepository(db_session)


@pytest.fixture
def test_sandbox(
    db_session: Session,
    test_workspace: Workspace,
    repository: SandboxInstanceRepository,
) -> SandboxInstance:
    """Create a test sandbox instance."""
    sandbox = repository.create(
        workspace_id=test_workspace.id,
        profile=SandboxProfile.DAYTONA,
        provider_ref=f"daytona-{uuid4().hex[:8]}",
        idle_ttl_seconds=3600,
    )
    db_session.commit()
    return sandbox


class TestBridgeTokenRotation:
    """Tests for bridge token rotation with grace period."""

    def test_rotate_bridge_token_sets_new_current(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that rotation sets the new token as current."""
        # Arrange
        old_token = "old-token-123"
        test_sandbox.bridge_auth_token = old_token
        db_session.commit()

        new_token = "new-token-456"

        # Act
        result = repository.rotate_bridge_token(test_sandbox.id, new_token, grace_seconds=30)

        # Assert
        assert result is not None
        assert result.bridge_auth_token == new_token

    def test_rotate_bridge_token_preserves_old_in_grace_slot(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that rotation moves old token to previous slot with expiry."""
        # Arrange
        old_token = "old-token-123"
        test_sandbox.bridge_auth_token = old_token
        db_session.commit()

        new_token = "new-token-456"
        before_rotate = datetime.utcnow()

        # Act
        result = repository.rotate_bridge_token(test_sandbox.id, new_token, grace_seconds=30)

        # Assert
        assert result is not None
        assert result.bridge_auth_token_prev == old_token
        assert result.bridge_auth_token_prev_expires_at is not None
        # Expiry should be ~30 seconds from now
        assert result.bridge_auth_token_prev_expires_at > before_rotate + timedelta(seconds=29)
        assert result.bridge_auth_token_prev_expires_at < before_rotate + timedelta(seconds=31)

    def test_rotate_bridge_token_multiple_rotations(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that multiple rotations maintain only one previous token."""
        # Arrange
        test_sandbox.bridge_auth_token = "token-1"
        db_session.commit()

        # Act
        repository.rotate_bridge_token(test_sandbox.id, "token-2", grace_seconds=30)
        db_session.commit()
        repository.rotate_bridge_token(test_sandbox.id, "token-3", grace_seconds=30)
        db_session.commit()
        repository.rotate_bridge_token(test_sandbox.id, "token-4", grace_seconds=30)
        db_session.commit()

        # Refresh from DB
        result = repository.get_by_id(test_sandbox.id)

        # Assert
        assert result is not None
        assert result.bridge_auth_token == "token-4"
        assert result.bridge_auth_token_prev == "token-3"

    def test_resolve_bridge_tokens_returns_current(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that resolve returns the current token."""
        # Arrange
        current_token = "current-token-abc"
        test_sandbox.bridge_auth_token = current_token
        db_session.commit()

        # Act
        tokens = repository.resolve_bridge_tokens(test_sandbox.id)

        # Assert
        assert tokens["current"] == current_token

    def test_resolve_bridge_tokens_returns_valid_previous(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that resolve returns previous token while within grace period."""
        # Arrange
        test_sandbox.bridge_auth_token = "new-token"
        test_sandbox.bridge_auth_token_prev = "old-token"
        test_sandbox.bridge_auth_token_prev_expires_at = datetime.utcnow() + timedelta(seconds=30)
        db_session.commit()

        # Act
        tokens = repository.resolve_bridge_tokens(test_sandbox.id)

        # Assert
        assert tokens["current"] == "new-token"
        assert tokens["previous"] == "old-token"
        assert tokens["previous_expires_at"] is not None

    def test_resolve_bridge_tokens_excludes_expired_previous(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that resolve excludes previous token after grace expiry."""
        # Arrange
        test_sandbox.bridge_auth_token = "new-token"
        test_sandbox.bridge_auth_token_prev = "old-token"
        test_sandbox.bridge_auth_token_prev_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db_session.commit()

        # Act
        tokens = repository.resolve_bridge_tokens(test_sandbox.id)

        # Assert
        assert tokens["current"] == "new-token"
        assert tokens["previous"] is None
        assert tokens["previous_expires_at"] is None

    def test_resolve_bridge_tokens_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that resolve returns empty result for non-existent sandbox."""
        # Act
        tokens = repository.resolve_bridge_tokens(uuid4())

        # Assert
        assert tokens["current"] is None
        assert tokens["previous"] is None
        assert tokens["previous_expires_at"] is None

    def test_rotate_bridge_token_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that rotation returns None for non-existent sandbox."""
        # Act
        result = repository.rotate_bridge_token(uuid4(), "new-token", grace_seconds=30)

        # Assert
        assert result is None


class TestGatewayUrlAuthority:
    """Tests for authoritative gateway URL management."""

    def test_set_gateway_url_authoritative_updates_url(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that authority method updates the gateway URL."""
        # Arrange
        authoritative_url = "https://gateway.daytona.example.com/sandbox-123"

        # Act
        result = repository.set_gateway_url_authoritative(test_sandbox.id, authoritative_url)

        # Assert
        assert result is not None
        assert result.gateway_url == authoritative_url

        # Verify persistence
        db_session.refresh(test_sandbox)
        assert test_sandbox.gateway_url == authoritative_url

    def test_set_gateway_url_authoritative_replaces_placeholder(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that authority URL replaces previous placeholder values."""
        # Arrange
        test_sandbox.gateway_url = "placeholder://temporary"
        db_session.commit()

        authoritative_url = "https://gateway.daytona.example.com/sandbox-123"

        # Act
        result = repository.set_gateway_url_authoritative(test_sandbox.id, authoritative_url)

        # Assert
        assert result is not None
        assert result.gateway_url == authoritative_url

    def test_set_gateway_url_authoritative_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that authority method returns None for non-existent sandbox."""
        # Act
        result = repository.set_gateway_url_authoritative(uuid4(), "https://example.com")

        # Assert
        assert result is None


class TestIdentityReadiness:
    """Tests for identity readiness state management."""

    def test_set_identity_ready_defaults_to_false(
        self,
        test_sandbox: SandboxInstance,
    ):
        """Test that new sandboxes default to identity_not_ready."""
        # Assert
        assert test_sandbox.identity_ready is False

    def test_set_identity_ready_to_true(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test setting identity ready to True."""
        # Act
        result = repository.set_identity_ready(test_sandbox.id, ready=True)

        # Assert
        assert result is not None
        assert result.identity_ready is True

        # Verify persistence
        db_session.refresh(test_sandbox)
        assert test_sandbox.identity_ready is True

    def test_set_identity_ready_to_false(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test setting identity ready to False."""
        # Arrange
        test_sandbox.identity_ready = True
        db_session.commit()

        # Act
        result = repository.set_identity_ready(test_sandbox.id, ready=False)

        # Assert
        assert result is not None
        assert result.identity_ready is False

    def test_set_identity_ready_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that setting identity ready returns None for non-existent sandbox."""
        # Act
        result = repository.set_identity_ready(uuid4(), ready=True)

        # Assert
        assert result is None

    def test_list_identity_not_ready(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test listing sandboxes where identity is not ready."""
        # Arrange
        test_sandbox.identity_ready = False
        db_session.commit()

        # Act
        not_ready = repository.list_identity_not_ready(workspace_id=test_workspace.id)

        # Assert
        assert len(not_ready) == 1
        assert not_ready[0].id == test_sandbox.id

    def test_list_identity_not_ready_empty_when_ready(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that listing excludes sandboxes with identity ready."""
        # Arrange
        test_sandbox.identity_ready = True
        db_session.commit()

        # Act
        not_ready = repository.list_identity_not_ready(workspace_id=test_workspace.id)

        # Assert
        assert len(not_ready) == 0


class TestHydrationStatus:
    """Tests for checkpoint hydration state management."""

    def test_hydration_status_defaults_to_pending(
        self,
        test_sandbox: SandboxInstance,
    ):
        """Test that new sandboxes default to pending hydration."""
        # Assert
        assert test_sandbox.hydration_status == SandboxHydrationStatus.PENDING
        assert test_sandbox.hydration_retry_count == 0

    def test_set_hydration_status_to_in_progress(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test setting hydration status to in_progress."""
        # Act
        result = repository.set_hydration_status(
            test_sandbox.id,
            status=SandboxHydrationStatus.IN_PROGRESS,
        )

        # Assert
        assert result is not None
        assert result.hydration_status == SandboxHydrationStatus.IN_PROGRESS

        # Verify persistence
        db_session.refresh(test_sandbox)
        assert test_sandbox.hydration_status == SandboxHydrationStatus.IN_PROGRESS

    def test_set_hydration_status_to_completed_resets_retry(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that completing hydration resets retry count and clears error."""
        # Arrange
        test_sandbox.hydration_retry_count = 3
        test_sandbox.hydration_last_error = "Previous failure"
        test_sandbox.hydration_status = SandboxHydrationStatus.DEGRADED
        db_session.commit()

        # Act
        result = repository.set_hydration_status(
            test_sandbox.id,
            status=SandboxHydrationStatus.COMPLETED,
        )

        # Assert
        assert result is not None
        assert result.hydration_status == SandboxHydrationStatus.COMPLETED
        assert result.hydration_retry_count == 0
        assert result.hydration_last_error is None

    def test_set_hydration_status_with_error(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test setting hydration status with error message."""
        # Act
        error_msg = "Failed to restore checkpoint: timeout"
        result = repository.set_hydration_status(
            test_sandbox.id,
            status=SandboxHydrationStatus.FAILED,
            last_error=error_msg,
        )

        # Assert
        assert result is not None
        assert result.hydration_status == SandboxHydrationStatus.FAILED
        assert result.hydration_last_error == error_msg

    def test_set_hydration_status_invalid_status(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
    ):
        """Test that invalid hydration status raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid hydration status"):
            repository.set_hydration_status(test_sandbox.id, status="invalid_status")

    def test_set_hydration_status_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that setting hydration status returns None for non-existent sandbox."""
        # Act
        result = repository.set_hydration_status(uuid4(), status=SandboxHydrationStatus.COMPLETED)

        # Assert
        assert result is None

    def test_increment_hydration_retry(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test incrementing hydration retry counter."""
        # Arrange
        initial_count = test_sandbox.hydration_retry_count

        # Act
        result = repository.increment_hydration_retry(test_sandbox.id)

        # Assert
        assert result is not None
        assert result.hydration_retry_count == initial_count + 1

        # Verify persistence
        db_session.refresh(test_sandbox)
        assert test_sandbox.hydration_retry_count == initial_count + 1

    def test_increment_hydration_retry_with_error(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test incrementing retry with error message."""
        # Arrange
        error_msg = "Network timeout during hydration"

        # Act
        result = repository.increment_hydration_retry(test_sandbox.id, error=error_msg)

        # Assert
        assert result is not None
        assert result.hydration_retry_count == 1
        assert result.hydration_last_error == error_msg

    def test_increment_hydration_retry_multiple(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test multiple retry increments."""
        # Act
        for i in range(5):
            result = repository.increment_hydration_retry(test_sandbox.id)
            db_session.commit()

        # Assert
        assert result is not None
        assert result.hydration_retry_count == 5

    def test_increment_hydration_retry_missing_sandbox(
        self,
        repository: SandboxInstanceRepository,
    ):
        """Test that incrementing retry returns None for non-existent sandbox."""
        # Act
        result = repository.increment_hydration_retry(uuid4())

        # Assert
        assert result is None

    def test_list_hydration_degraded(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test listing sandboxes with degraded hydration."""
        # Arrange
        test_sandbox.hydration_status = SandboxHydrationStatus.DEGRADED
        db_session.commit()

        # Act
        degraded = repository.list_hydration_degraded(workspace_id=test_workspace.id)

        # Assert
        assert len(degraded) == 1
        assert degraded[0].id == test_sandbox.id

    def test_list_hydration_degraded_includes_failed(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test listing includes failed hydration status."""
        # Arrange
        test_sandbox.hydration_status = SandboxHydrationStatus.FAILED
        db_session.commit()

        # Act
        degraded = repository.list_hydration_degraded(workspace_id=test_workspace.id)

        # Assert
        assert len(degraded) == 1
        assert degraded[0].hydration_status == SandboxHydrationStatus.FAILED

    def test_list_hydration_degraded_excludes_healthy(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that listing excludes sandboxes with completed hydration."""
        # Arrange
        test_sandbox.hydration_status = SandboxHydrationStatus.COMPLETED
        db_session.commit()

        # Act
        degraded = repository.list_hydration_degraded(workspace_id=test_workspace.id)

        # Assert
        assert len(degraded) == 0


class TestFailClosedBehavior:
    """Tests for fail-closed behavior on missing tokens/gateway."""

    def test_resolve_bridge_tokens_fails_closed_no_tokens(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
    ):
        """Test that resolve returns None when no tokens are set."""
        # Act
        tokens = repository.resolve_bridge_tokens(test_sandbox.id)

        # Assert - all None when no tokens configured
        assert tokens["current"] is None
        assert tokens["previous"] is None
        assert tokens["previous_expires_at"] is None

    def test_new_sandbox_has_no_bridge_token(
        self,
        test_sandbox: SandboxInstance,
    ):
        """Test that newly created sandboxes have no bridge token."""
        # Assert - fail closed: no token until explicitly set
        assert test_sandbox.bridge_auth_token is None
        assert test_sandbox.bridge_auth_token_prev is None
        assert test_sandbox.bridge_auth_token_prev_expires_at is None

    def test_new_sandbox_has_no_gateway_url(
        self,
        test_sandbox: SandboxInstance,
    ):
        """Test that newly created sandboxes have no gateway URL."""
        # Assert - fail closed: no URL until explicitly set
        assert test_sandbox.gateway_url is None

    def test_identity_not_ready_blocks_requests(
        self,
        test_sandbox: SandboxInstance,
    ):
        """Test that identity_not_ready defaults to blocking state."""
        # Assert - fail closed: identity not ready by default
        assert test_sandbox.identity_ready is False


class TestHydrationPersistence:
    """Tests for hydration state persistence across updates."""

    def test_hydration_state_persists_across_other_updates(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that hydration state survives unrelated updates."""
        # Arrange
        test_sandbox.hydration_status = SandboxHydrationStatus.IN_PROGRESS
        test_sandbox.hydration_retry_count = 2
        test_sandbox.hydration_last_error = "Timeout"
        db_session.commit()

        # Act - update unrelated field
        repository.update_health(test_sandbox.id, SandboxHealthStatus.HEALTHY)
        db_session.commit()

        # Refresh and check
        result = repository.get_by_id(test_sandbox.id)

        # Assert - hydration state preserved
        assert result is not None
        assert result.hydration_status == SandboxHydrationStatus.IN_PROGRESS
        assert result.hydration_retry_count == 2
        assert result.hydration_last_error == "Timeout"

    def test_bridge_token_persists_across_state_updates(
        self,
        repository: SandboxInstanceRepository,
        test_sandbox: SandboxInstance,
        db_session: Session,
    ):
        """Test that bridge token survives state transitions."""
        # Arrange
        test_sandbox.bridge_auth_token = "persistent-token-123"
        db_session.commit()

        # Act - update state
        repository.update_state(test_sandbox.id, SandboxState.ACTIVE)
        db_session.commit()

        # Refresh and check
        result = repository.get_by_id(test_sandbox.id)

        # Assert - token preserved
        assert result is not None
        assert result.bridge_auth_token == "persistent-token-123"


class TestExternalUserIdPersistence:
    """Tests for external_user_id persistence and filtering in per-user sandbox routing."""

    def test_create_persists_external_user_id(
        self,
        repository: SandboxInstanceRepository,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that create persists external_user_id on the SandboxInstance row."""
        # Act
        sandbox = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id="user-123",
            idle_ttl_seconds=3600,
        )
        db_session.commit()

        # Assert
        assert sandbox is not None
        assert sandbox.external_user_id == "user-123"

        # Verify persistence via fetch
        result = repository.get_by_id(sandbox.id)
        assert result is not None
        assert result.external_user_id == "user-123"

    def test_list_active_healthy_filters_by_external_user_id(
        self,
        repository: SandboxInstanceRepository,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that list_active_healthy_by_workspace returns only sandboxes for the specified external_user_id."""
        # Arrange - create sandboxes for two users in the same workspace
        sandbox_user_a = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id="user-a",
            idle_ttl_seconds=3600,
        )
        sandbox_user_a.state = SandboxState.ACTIVE
        sandbox_user_a.health_status = SandboxHealthStatus.HEALTHY
        sandbox_user_a.identity_ready = True

        sandbox_user_b = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id="user-b",
            idle_ttl_seconds=3600,
        )
        sandbox_user_b.state = SandboxState.ACTIVE
        sandbox_user_b.health_status = SandboxHealthStatus.HEALTHY
        sandbox_user_b.identity_ready = True

        # Create a sandbox without external_user_id (e.g., API-key based)
        sandbox_no_user = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id=None,
            idle_ttl_seconds=3600,
        )
        sandbox_no_user.state = SandboxState.ACTIVE
        sandbox_no_user.health_status = SandboxHealthStatus.HEALTHY
        sandbox_no_user.identity_ready = True

        db_session.commit()

        # Act - query for user-a
        results_user_a = repository.list_active_healthy_by_workspace(
            workspace_id=test_workspace.id,
            external_user_id="user-a",
        )

        # Assert - should only return sandbox for user-a
        assert len(results_user_a) == 1
        assert results_user_a[0].id == sandbox_user_a.id
        assert results_user_a[0].external_user_id == "user-a"

        # Act - query for user-b
        results_user_b = repository.list_active_healthy_by_workspace(
            workspace_id=test_workspace.id,
            external_user_id="user-b",
        )

        # Assert - should only return sandbox for user-b
        assert len(results_user_b) == 1
        assert results_user_b[0].id == sandbox_user_b.id

        # Act - query without external_user_id filter (backwards compatibility)
        results_all = repository.list_active_healthy_by_workspace(
            workspace_id=test_workspace.id,
        )

        # Assert - should return all active healthy sandboxes
        assert len(results_all) == 3

    def test_list_by_workspace_filters_by_external_user_id(
        self,
        repository: SandboxInstanceRepository,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that list_by_workspace filters by external_user_id when provided."""
        # Arrange
        sandbox_user_a = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id="user-a",
            idle_ttl_seconds=3600,
        )
        sandbox_user_a.state = SandboxState.ACTIVE

        sandbox_user_b = repository.create(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            external_user_id="user-b",
            idle_ttl_seconds=3600,
        )
        sandbox_user_b.state = SandboxState.ACTIVE

        db_session.commit()

        # Act - query for user-a
        results_user_a = repository.list_by_workspace(
            workspace_id=test_workspace.id,
            external_user_id="user-a",
        )

        # Assert
        assert len(results_user_a) == 1
        assert results_user_a[0].external_user_id == "user-a"

        # Act - query without filter
        results_all = repository.list_by_workspace(
            workspace_id=test_workspace.id,
        )

        # Assert - should return all
        assert len(results_all) == 2

    def test_list_active_healthy_excludes_other_users_same_workspace(
        self,
        repository: SandboxInstanceRepository,
        test_workspace: Workspace,
        db_session: Session,
    ):
        """Test that query excludes sandboxes belonging to other users in the same workspace."""
        # Arrange - multiple users in same workspace
        for user_id in ["alice", "bob", "charlie"]:
            sandbox = repository.create(
                workspace_id=test_workspace.id,
                profile=SandboxProfile.DAYTONA,
                external_user_id=user_id,
                idle_ttl_seconds=3600,
            )
            sandbox.state = SandboxState.ACTIVE
            sandbox.health_status = SandboxHealthStatus.HEALTHY
            sandbox.identity_ready = True

        db_session.commit()

        # Act - query for only alice
        results = repository.list_active_healthy_by_workspace(
            workspace_id=test_workspace.id,
            external_user_id="alice",
        )

        # Assert - only alice's sandbox returned
        assert len(results) == 1
        assert results[0].external_user_id == "alice"

        # Verify bob and charlie are excluded
        bob_results = repository.list_active_healthy_by_workspace(
            workspace_id=test_workspace.id,
            external_user_id="bob",
        )
        assert len(bob_results) == 1
        assert bob_results[0].external_user_id == "bob"
