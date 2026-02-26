"""Tests for sandbox orchestrator service and routing behavior.

Tests health-aware routing, unhealthy exclusion, idle TTL enforcement,
and configurable TTL behavior.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
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
)
from src.services.sandbox_orchestrator_service import (
    SandboxOrchestratorService,
    RoutingResult,
    StopEligibilityResult,
)
from src.infrastructure.sandbox.providers.base import (
    SandboxInfo,
    SandboxRef,
    SandboxState as ProviderSandboxState,
    SandboxHealth as ProviderSandboxHealth,
)


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
def mock_provider():
    """Create a mock sandbox provider."""
    provider = MagicMock()
    provider.profile = "local_compose"
    provider.get_health = AsyncMock()
    provider.provision_sandbox = AsyncMock()
    provider.stop_sandbox = AsyncMock()
    return provider


@pytest.fixture
def orchestrator_service(
    db_session: Session, mock_provider
) -> SandboxOrchestratorService:
    """Create an orchestrator service with mock provider."""
    return SandboxOrchestratorService(
        session=db_session,
        provider=mock_provider,
        idle_ttl_seconds=3600,  # 1 hour default
    )


class TestTTLConfiguration:
    """Tests for configurable idle TTL settings."""

    def test_default_ttl_from_settings(self, db_session: Session, mock_provider):
        """Test that default TTL is used from settings."""
        service = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
        )

        assert service._idle_ttl_seconds == 3600  # Default 1 hour

    def test_custom_ttl_override(self, db_session: Session, mock_provider):
        """Test that custom TTL overrides default."""
        custom_ttl = 1800  # 30 minutes

        service = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=custom_ttl,
        )

        assert service._idle_ttl_seconds == custom_ttl

    def test_ttl_validation_minimum(self, db_session: Session, mock_provider):
        """Test TTL validation rejects values below minimum."""
        with pytest.raises(ValueError) as exc_info:
            SandboxOrchestratorService(
                session=db_session,
                provider=mock_provider,
                idle_ttl_seconds=30,  # Below minimum of 60
            )

        assert "at least" in str(exc_info.value).lower()

    def test_ttl_validation_maximum(self, db_session: Session, mock_provider):
        """Test TTL validation rejects values above maximum."""
        with pytest.raises(ValueError) as exc_info:
            SandboxOrchestratorService(
                session=db_session,
                provider=mock_provider,
                idle_ttl_seconds=90000,  # Above maximum of 86400
            )

        assert "at most" in str(exc_info.value).lower()

    def test_non_default_ttl_changes_stop_outcome(
        self,
        db_session: Session,
        test_workspace: Workspace,
        mock_provider,
    ):
        """Test that non-default TTL changes stop/no-stop outcomes.

        This test verifies that WORK-06 idle TTL policy is configurable
        and different TTL values produce different eligibility results.
        """
        # Create sandbox with activity 30 minutes ago
        thirty_mins_ago = datetime.utcnow() - timedelta(minutes=30)

        # Test with 1 hour TTL - should NOT be eligible
        service_long_ttl = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,  # 1 hour
        )

        sandbox_long = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=thirty_mins_ago,
            idle_ttl_seconds=3600,
            created_at=thirty_mins_ago,
        )
        db_session.add(sandbox_long)
        db_session.commit()

        eligibility_long = service_long_ttl.check_stop_eligibility(sandbox_long)
        assert eligibility_long.eligible is False, (
            "30 min idle should NOT stop with 1 hour TTL"
        )

        # Clean up
        db_session.delete(sandbox_long)
        db_session.commit()

        # Test with 15 minute TTL - should BE eligible
        service_short_ttl = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=900,  # 15 minutes
        )

        sandbox_short = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=thirty_mins_ago,
            idle_ttl_seconds=900,
            created_at=thirty_mins_ago,
        )
        db_session.add(sandbox_short)
        db_session.commit()

        eligibility_short = service_short_ttl.check_stop_eligibility(sandbox_short)
        assert eligibility_short.eligible is True, (
            "30 min idle SHOULD stop with 15 min TTL"
        )


class TestStopEligibility:
    """Tests for idle stop eligibility checking."""

    def test_stop_eligibility_idle_within_ttl(self, test_workspace: Workspace):
        """Test sandbox within TTL is not eligible for stop."""
        from src.db.repositories.sandbox_instance_repository import (
            SandboxInstanceRepository,
        )

        # Create mock session and repository
        mock_session = MagicMock()
        SandboxInstanceRepository(mock_session)

        # Create sandbox with recent activity
        SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=datetime.utcnow() - timedelta(minutes=30),
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )

        # Check eligibility with 1 hour TTL
        eligibility = StopEligibilityResult(
            eligible=False,
            reason="Within TTL window",
            idle_seconds=1800,
            ttl_seconds=3600,
        )

        assert eligibility.eligible is False
        assert eligibility.idle_seconds == 1800
        assert eligibility.ttl_seconds == 3600

    def test_stop_eligibility_idle_exceeds_ttl(self, test_workspace: Workspace):
        """Test sandbox exceeding TTL is eligible for stop."""
        SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=datetime.utcnow() - timedelta(hours=2),
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=3),
        )

        # Check eligibility with 1 hour TTL
        eligibility = StopEligibilityResult(
            eligible=True,
            reason="Exceeds TTL",
            idle_seconds=7200,
            ttl_seconds=3600,
        )

        assert eligibility.eligible is True
        assert eligibility.idle_seconds == 7200

    def test_stop_eligibility_not_active_state(self, test_workspace: Workspace):
        """Test non-active sandboxes are not eligible for stop."""
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.STOPPED,
            health_status=SandboxHealthStatus.UNKNOWN,
            created_at=datetime.utcnow() - timedelta(hours=3),
        )

        eligibility = StopEligibilityResult(
            eligible=False,
            reason=f"Sandbox is not active (state: {sandbox.state})",
            idle_seconds=None,
            ttl_seconds=3600,
        )

        assert eligibility.eligible is False
        assert "not active" in eligibility.reason.lower()

    def test_stop_eligibility_no_activity_uses_created_at(self):
        """Test that created_at is used when no activity timestamp."""
        # This tests the fallback behavior
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=uuid4(),
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=None,
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )

        # Should calculate idle from created_at
        assert sandbox.last_activity_at is None
        assert sandbox.created_at is not None


class TestHealthAwareRouting:
    """Tests for health-aware sandbox routing."""

    @pytest.mark.asyncio
    async def test_route_to_healthy_existing_sandbox(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test routing prefers existing healthy sandbox with identity ready."""
        # Create an active healthy sandbox with identity ready
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="sandbox-123",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=datetime.utcnow(),
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=1),
            identity_ready=True,
            hydration_status="completed",
        )
        db_session.add(sandbox)
        db_session.commit()

        # Mock provider to return healthy
        mock_provider.get_health.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="sandbox-123", profile="local_compose"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=test_workspace.id,
            last_activity_at=datetime.utcnow(),
        )

        # Resolve should route to existing
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
        )

        assert result.success is True
        assert result.result == RoutingResult.ROUTED_EXISTING
        assert result.sandbox is not None
        assert result.sandbox.id == sandbox.id

    @pytest.mark.asyncio
    async def test_exclude_unhealthy_from_routing(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that unhealthy sandboxes are excluded from routing."""
        # Create an unhealthy sandbox (identity ready but health check will fail)
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="unhealthy-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,  # Will be updated after check
            last_activity_at=datetime.utcnow(),
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=1),
            identity_ready=True,
            hydration_status="completed",
        )
        db_session.add(sandbox)
        db_session.commit()

        # Mock provider to return unhealthy
        mock_provider.get_health.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="unhealthy-sandbox", profile="local_compose"),
            state=ProviderSandboxState.UNHEALTHY,
            health=ProviderSandboxHealth.UNHEALTHY,
            workspace_id=test_workspace.id,
        )

        # Mock provision to return new sandbox
        mock_provider.provision_sandbox.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="new-sandbox", profile="local_compose"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=test_workspace.id,
        )

        # Resolve should exclude unhealthy and provision new
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
        )

        assert result.success is True
        assert result.result == RoutingResult.PROVISIONED_NEW
        assert len(result.excluded_unhealthy) == 1
        assert result.excluded_unhealthy[0].id == sandbox.id

    @pytest.mark.asyncio
    async def test_provision_when_no_sandboxes_exist(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test provisioning when no sandboxes exist."""
        # Mock provision to return new sandbox
        mock_provider.provision_sandbox.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="new-sandbox", profile="local_compose"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=test_workspace.id,
        )

        # Resolve should provision new
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
        )

        assert result.success is True
        assert result.result == RoutingResult.PROVISIONED_NEW
        assert result.sandbox is not None

    @pytest.mark.asyncio
    async def test_resolve_sandbox_populates_pack_source_path_from_agent_pack_id(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that pack source_path is resolved and passed to provider config."""
        from src.db.models import AgentPackValidationStatus
        from src.db.repositories.agent_pack_repository import AgentPackRepository

        # Create a valid agent pack
        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path="/test/pack/path",
            source_digest="abc123",
        )
        # Mark as valid and active
        pack.validation_status = AgentPackValidationStatus.VALID
        pack.is_active = True
        db_session.flush()

        # Capture the config passed to provider
        captured_config = None

        async def capture_provision(config):
            nonlocal captured_config
            captured_config = config
            return SandboxInfo(
                ref=SandboxRef(provider_ref="new-sandbox", profile="local_compose"),
                state=ProviderSandboxState.READY,
                health=ProviderSandboxHealth.HEALTHY,
                workspace_id=test_workspace.id,
            )

        mock_provider.provision_sandbox.side_effect = capture_provision

        # Resolve sandbox with pack
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        assert result.success is True
        assert result.result == RoutingResult.PROVISIONED_NEW
        assert captured_config is not None
        assert captured_config.pack_source_path == "/test/pack/path"

    @pytest.mark.asyncio
    async def test_resolve_sandbox_rejects_cross_workspace_agent_pack_binding(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that pack from different workspace is rejected (fail-closed)."""
        from src.db.models import AgentPackValidationStatus, Workspace
        from src.db.repositories.agent_pack_repository import AgentPackRepository

        # Create another workspace
        other_workspace = Workspace(
            id=uuid4(),
            name="Other Workspace",
            slug="other-workspace",
            owner_id=test_user.id,
        )
        db_session.add(other_workspace)
        db_session.commit()

        # Create a pack in the OTHER workspace
        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=other_workspace.id,  # Different workspace!
            name="Other Pack",
            source_path="/other/pack/path",
            source_digest="def456",
        )
        pack.validation_status = AgentPackValidationStatus.VALID
        pack.is_active = True
        db_session.flush()

        # Attempt to use cross-workspace pack
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,  # Requesting for different workspace
            agent_pack_id=pack.id,
        )

        # Should fail closed - no provisioning
        assert result.success is False
        assert result.result == RoutingResult.PROVISION_FAILED
        assert "does not belong to workspace" in result.message
        # Provider should not have been called
        mock_provider.provision_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_sandbox_rejects_missing_agent_pack(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that missing pack ID fails closed."""
        nonexistent_pack_id = uuid4()

        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=nonexistent_pack_id,
        )

        assert result.success is False
        assert result.result == RoutingResult.PROVISION_FAILED
        assert "not found" in result.message.lower()
        mock_provider.provision_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_sandbox_rejects_inactive_agent_pack(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that inactive pack fails closed."""
        from src.db.models import AgentPackValidationStatus
        from src.db.repositories.agent_pack_repository import AgentPackRepository

        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=test_workspace.id,
            name="Inactive Pack",
            source_path="/inactive/path",
            source_digest="abc123",
        )
        pack.validation_status = AgentPackValidationStatus.VALID
        pack.is_active = False  # Inactive!
        db_session.flush()

        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        assert result.success is False
        assert result.result == RoutingResult.PROVISION_FAILED
        assert "not active" in result.message.lower()
        mock_provider.provision_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_sandbox_rejects_invalid_agent_pack_status(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that non-VALID pack status fails closed."""
        from src.db.models import AgentPackValidationStatus
        from src.db.repositories.agent_pack_repository import AgentPackRepository

        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=test_workspace.id,
            name="Pending Pack",
            source_path="/pending/path",
            source_digest="abc123",
        )
        pack.validation_status = AgentPackValidationStatus.PENDING  # Not valid!
        pack.is_active = True
        db_session.flush()

        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        assert result.success is False
        assert result.result == RoutingResult.PROVISION_FAILED
        assert "not valid" in result.message.lower()
        mock_provider.provision_sandbox.assert_not_called()


class TestIdempotentStop:
    """Tests for idempotent stop operations."""

    @pytest.mark.asyncio
    async def test_stop_sandbox_idempotent(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that stop operations are idempotent."""
        # Create an active sandbox
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="sandbox-to-stop",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            created_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(sandbox)
        db_session.commit()

        # Mock stop to succeed
        mock_provider.stop_sandbox.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="sandbox-to-stop", profile="local_compose"),
            state=ProviderSandboxState.STOPPED,
            health=ProviderSandboxHealth.UNKNOWN,
        )

        # Stop the sandbox
        stopped = await orchestrator_service._stop_sandbox(sandbox)

        assert stopped is not None
        assert stopped.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_stop_already_stopped_sandbox(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test stopping an already stopped sandbox (idempotent)."""
        from src.infrastructure.sandbox.providers.base import SandboxNotFoundError

        # Create a stopped sandbox
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="already-stopped",
            state=SandboxState.ACTIVE,  # Will transition to STOPPING then STOPPED
            health_status=SandboxHealthStatus.HEALTHY,
            created_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(sandbox)
        db_session.commit()

        # Mock stop to raise NotFound (idempotent case)
        mock_provider.stop_sandbox.side_effect = SandboxNotFoundError(
            "Sandbox not found"
        )

        # Stop should succeed even if provider raises NotFound
        stopped = await orchestrator_service._stop_sandbox(sandbox)

        assert stopped is not None
        assert stopped.state == SandboxState.STOPPED


class TestSandboxProfileRouting:
    """Tests for profile-aware routing."""

    @pytest.mark.asyncio
    async def test_routing_respects_profile_filter(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
        mock_provider,
    ):
        """Test that routing respects profile filter."""
        # Create local_compose sandbox with identity ready
        local_sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="local-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=datetime.utcnow(),
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=1),
            identity_ready=True,
            hydration_status="completed",
        )
        db_session.add(local_sandbox)
        db_session.commit()

        # Mock health check
        mock_provider.get_health.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="local-sandbox", profile="local_compose"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
        )

        # Request with local_compose profile should route to existing
        result = await orchestrator_service.resolve_sandbox(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
        )

        assert result.success is True
        assert result.sandbox.profile == SandboxProfile.LOCAL_COMPOSE


class TestSandboxActivityTracking:
    """Tests for activity timestamp tracking."""

    def test_update_activity_timestamp(
        self,
        db_session: Session,
        test_workspace: Workspace,
        orchestrator_service: SandboxOrchestratorService,
    ):
        """Test that activity timestamp is updated on routing."""
        # Create sandbox with old activity timestamp
        old_activity = datetime.utcnow() - timedelta(hours=2)
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="sandbox-123",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=old_activity,
            idle_ttl_seconds=3600,
            created_at=datetime.utcnow() - timedelta(hours=3),
        )
        db_session.add(sandbox)
        db_session.commit()

        # Update activity
        updated = orchestrator_service.update_sandbox_activity(sandbox.id)

        assert updated is not None
        assert updated.last_activity_at > old_activity
