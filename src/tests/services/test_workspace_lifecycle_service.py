"""Tests for workspace lifecycle service.

Tests workspace resolution, lease integration, sandbox routing,
and guaranteed lease cleanup in success/failure branches.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

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
from src.services.workspace_lifecycle_service import (
    WorkspaceLifecycleService,
    LifecycleTarget,
    LifecycleContext,
)
from src.services.workspace_lease_service import (
    WorkspaceLeaseService,
    LeaseResult,
)
from src.services.sandbox_orchestrator_service import (
    SandboxOrchestratorService,
    RoutingResult,
    SandboxRoutingResult,
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
def mock_orchestrator():
    """Create a mock orchestrator service."""
    orchestrator = MagicMock(spec=SandboxOrchestratorService)
    orchestrator.resolve_sandbox = AsyncMock()
    return orchestrator


@pytest.fixture
def lifecycle_service(
    db_session: Session, mock_orchestrator
) -> WorkspaceLifecycleService:
    """Create a lifecycle service with mock orchestrator."""
    return WorkspaceLifecycleService(
        session=db_session,
        orchestrator=mock_orchestrator,
    )


class TestWorkspaceResolution:
    """Tests for workspace resolution and auto-creation."""

    @pytest.mark.asyncio
    async def test_resolve_existing_workspace(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test resolving an existing workspace."""
        # Mock orchestrator to return success
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
        )

        assert target.workspace is not None
        assert target.workspace.id == test_workspace.id
        assert target.error is None

    @pytest.mark.asyncio
    async def test_auto_create_workspace(
        self,
        db_session: Session,
        test_user: User,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test auto-creating workspace for new user."""
        # Mock orchestrator
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
        )

        assert target.workspace is not None
        assert target.workspace.owner_id == test_user.id

    @pytest.mark.asyncio
    async def test_no_auto_create_when_disabled(
        self,
        db_session: Session,
        test_user: User,
        lifecycle_service: WorkspaceLifecycleService,
    ):
        """Test that workspace is not created when auto_create is False."""
        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=False,
            acquire_lease=False,
        )

        assert target.workspace is None
        assert target.error is not None
        assert (
            "auto_create" in target.error.lower() or "not found" in target.error.lower()
        )


class TestLeaseIntegration:
    """Tests for lease acquisition and release integration."""

    @pytest.mark.asyncio
    async def test_acquire_lease_on_resolve(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test that lease is acquired during resolution."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
        )

        assert target.lease_acquired is True
        assert target.lease_result is not None
        assert target.lease_result.success is True

    @pytest.mark.asyncio
    async def test_skip_lease_when_disabled(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test that lease is skipped when acquire_lease is False."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
        )

        assert target.lease_acquired is False
        assert target.lease_result is None

    @pytest.mark.asyncio
    async def test_lease_conflict_returns_early(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        db_session2: Session = None,  # Will need separate session for conflict
    ):
        """Test that lease conflict prevents sandbox resolution."""
        # First, acquire a lease manually
        lease_service = WorkspaceLeaseService(db_session)
        lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="other-run",
            holder_identity="other-user",
        )
        db_session.commit()

        # Now try to resolve - should get conflict
        lifecycle = WorkspaceLifecycleService(db_session)
        target = await lifecycle.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
        )

        assert target.lease_acquired is False
        assert target.lease_result is not None
        assert target.lease_result.result == LeaseResult.CONFLICT
        # Should not have attempted sandbox resolution
        assert target.routing_result is None

    def test_release_lease_explicit(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
    ):
        """Test explicit lease release."""
        # Acquire lease first
        lease_service = WorkspaceLeaseService(db_session)
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="test-run",
            holder_identity=str(test_user.id),
        )
        assert acquire_result.success is True
        db_session.commit()

        # Release via lifecycle service
        release_result = lifecycle_service.release_lease(
            workspace_id=test_workspace.id,
            run_id="test-run",
        )

        assert release_result.success is True
        assert release_result.result == LeaseResult.RELEASED


class TestSandboxRoutingIntegration:
    """Tests for sandbox routing integration."""

    @pytest.mark.asyncio
    async def test_resolve_target_passes_agent_pack_id_to_orchestrator(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test that agent_pack_id is forwarded from lifecycle to orchestrator."""
        from uuid import uuid4, UUID

        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        pack_id = str(uuid4())
        await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
            agent_pack_id=pack_id,
        )

        # Verify orchestrator was called with agent_pack_id (converted to UUID)
        mock_orchestrator.resolve_sandbox.assert_called_once()
        call_kwargs = mock_orchestrator.resolve_sandbox.call_args.kwargs
        assert call_kwargs.get("agent_pack_id") == UUID(pack_id)

    @pytest.mark.asyncio
    async def test_resolve_with_sandbox_routing(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test full resolution with sandbox routing."""
        # Create a mock sandbox
        mock_sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
        )

        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=mock_sandbox,
            provider_info=SandboxInfo(
                ref=SandboxRef(provider_ref="sandbox-123", profile="local_compose"),
                state=ProviderSandboxState.READY,
                health=ProviderSandboxHealth.HEALTHY,
            ),
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
        )

        assert target.workspace is not None
        assert target.lease_acquired is True
        assert target.sandbox is not None
        assert target.routing_result is not None
        assert target.routing_result.success is True

    @pytest.mark.asyncio
    async def test_routing_failure_handled(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test that routing failure is handled gracefully."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=False,
            result=RoutingResult.PROVISION_FAILED,
            sandbox=None,
            provider_info=None,
            message="Provisioning failed: no capacity",
            excluded_unhealthy=[],
        )

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
        )

        # Should still have workspace and lease
        assert target.workspace is not None
        assert target.lease_acquired is True
        # But no sandbox
        assert target.sandbox is None
        assert target.routing_result is not None
        assert target.routing_result.success is False
        assert target.error is not None


class TestDeterministicLeaseCleanup:
    """Tests for guaranteed lease cleanup."""

    @pytest.mark.asyncio
    async def test_lease_cleanup_on_success(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test lease is properly tracked and can be cleaned up on success."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        run_id = "test-run-success"
        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
            run_id=run_id,
        )

        assert target.lease_acquired is True

        # Simulate cleanup
        release_result = lifecycle_service.release_lease(
            workspace_id=target.workspace.id,
            run_id=run_id,
        )

        assert release_result.success is True

    @pytest.mark.asyncio
    async def test_lease_cleanup_on_failure(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test lease is released even when routing fails."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=False,
            result=RoutingResult.PROVISION_FAILED,
            sandbox=None,
            provider_info=None,
            message="Provisioning failed",
            excluded_unhealthy=[],
        )

        run_id = "test-run-failure"
        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
            run_id=run_id,
        )

        # Lease should still be acquired even if routing failed
        assert target.lease_acquired is True

        # Cleanup should still work
        release_result = lifecycle_service.release_lease(
            workspace_id=target.workspace.id,
            run_id=run_id,
        )

        assert release_result.success is True


class TestWorkspaceContinuity:
    """Tests for workspace continuity semantics."""

    @pytest.mark.asyncio
    async def test_workspace_reuse_across_calls(
        self,
        db_session: Session,
        test_user: User,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test that same workspace is returned across multiple calls."""
        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        # First call creates workspace
        target1 = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
        )

        # Second call should return same workspace
        target2 = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=False,
        )

        assert target1.workspace is not None
        assert target2.workspace is not None
        assert target1.workspace.id == target2.workspace.id

    @pytest.mark.asyncio
    async def test_ensure_workspace_api(
        self,
        db_session: Session,
        test_user: User,
        lifecycle_service: WorkspaceLifecycleService,
    ):
        """Test the ensure_workspace convenience method."""
        workspace = await lifecycle_service.ensure_workspace(test_user)

        assert workspace is not None
        assert workspace.owner_id == test_user.id

        # Second call should return same workspace
        workspace2 = await lifecycle_service.ensure_workspace(test_user)
        assert workspace2.id == workspace.id


class TestLifecycleContext:
    """Tests for lifecycle context management."""

    def test_lifecycle_context_release(
        self, db_session: Session, test_workspace: Workspace
    ):
        """Test that lifecycle context properly releases lease."""
        lease_service = WorkspaceLeaseService(db_session)

        # First acquire a lease
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="test-run",
            holder_identity="test-user",
        )
        assert acquire_result.success is True
        db_session.commit()

        context = LifecycleContext(
            workspace_id=test_workspace.id,
            run_id="test-run",
            lease_service=lease_service,
            acquired_lease=True,
        )

        # First release should work
        result1 = context.release()
        assert result1.success is True
        assert context.released is True

        # Second release should be idempotent
        result2 = context.release()
        assert result2.success is True

    def test_lifecycle_context_no_release_if_not_acquired(self, db_session: Session):
        """Test that context doesn't release if lease wasn't acquired."""
        lease_service = WorkspaceLeaseService(db_session)

        context = LifecycleContext(
            workspace_id=uuid4(),
            run_id="test-run",
            lease_service=lease_service,
            acquired_lease=False,
        )

        result = context.release()
        # Should succeed but indicate no action taken
        assert result.success is True


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_principal_handled(
        self,
        db_session: Session,
        lifecycle_service: WorkspaceLifecycleService,
    ):
        """Test handling of invalid principal."""
        # Principal with no ID
        invalid_principal = object()

        target = await lifecycle_service.resolve_target(
            principal=invalid_principal,
            auto_create=True,
        )

        # Should handle gracefully
        assert target.workspace is None or target.error is not None

    @pytest.mark.asyncio
    async def test_orchestrator_exception_handled(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        lifecycle_service: WorkspaceLifecycleService,
        mock_orchestrator,
    ):
        """Test handling of orchestrator exceptions."""
        mock_orchestrator.resolve_sandbox.side_effect = Exception("Provider error")

        target = await lifecycle_service.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
        )

        # Should handle exception gracefully
        assert target.workspace is not None
        assert target.lease_acquired is True
        # Routing should have failed but not crashed
        assert target.routing_result is not None
        assert target.routing_result.success is False


class TestServiceIntegration:
    """Tests for service-level integration with real dependencies."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_real_lease_service(
        self,
        db_session: Session,
        test_user: User,
        test_workspace: Workspace,
        mock_orchestrator,
    ):
        """Test full lifecycle with real lease service."""
        # Use real lease service, mock orchestrator
        lease_service = WorkspaceLeaseService(db_session)

        lifecycle = WorkspaceLifecycleService(
            session=db_session,
            lease_service=lease_service,
            orchestrator=mock_orchestrator,
        )

        mock_orchestrator.resolve_sandbox.return_value = SandboxRoutingResult(
            success=True,
            result=RoutingResult.ROUTED_EXISTING,
            sandbox=None,
            provider_info=None,
            message="Routed successfully",
            excluded_unhealthy=[],
        )

        run_id = "integration-test-run"
        target = await lifecycle.resolve_target(
            principal=test_user,
            auto_create=True,
            acquire_lease=True,
            run_id=run_id,
        )

        # Verify lease was actually acquired
        assert target.lease_acquired is True
        has_lease = lease_service.has_active_lease(test_workspace.id)
        assert has_lease is True

        # Verify lease holder is correct
        active_lease = lease_service.get_active_lease(test_workspace.id)
        assert active_lease is not None
        assert active_lease.holder_run_id == run_id

        # Cleanup
        lifecycle.release_lease(test_workspace.id, run_id)

        # Verify lease released
        has_lease_after = lease_service.has_active_lease(test_workspace.id)
        assert has_lease_after is False
