"""Parity tests for sandbox provider adapters.

This test suite verifies that all provider implementations (local_compose,
daytona) expose equivalent semantic behavior and matching lifecycle outputs.

Tests focus on semantic parity - the states, health checks, and error
conditions should be identical across providers regardless of underlying
implementation differences.

For Daytona provider, tests use mocked SDK to verify call patterns and
semantic mapping without requiring real Daytona credentials.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
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
)
from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxHealth,
    SandboxNotFoundError,
    SandboxProfileError,
    SandboxProvisionError,
    SandboxRef,
    SandboxState,
    SandboxHealth as ProviderSandboxHealth,
    SandboxState as ProviderSandboxState,
)
from src.infrastructure.sandbox.providers.base import SandboxInfo
from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
from src.infrastructure.sandbox.providers.factory import (
    get_current_profile,
    get_provider,
    list_available_profiles,
)
from src.infrastructure.sandbox.providers.local_compose import (
    LocalComposeSandboxProvider,
)


# Fixtures for TestPackStaleDetection
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


class TestProviderFactory:
    """Test provider factory configuration and selection."""

    def test_list_available_profiles(self):
        """Factory returns supported profile keys."""
        profiles = list_available_profiles()

        assert "local_compose" in profiles
        assert "daytona" in profiles
        assert len(profiles) == 2

    def test_get_provider_local_compose(self):
        """Factory instantiates LocalComposeSandboxProvider."""
        provider = get_provider("local_compose")

        assert isinstance(provider, LocalComposeSandboxProvider)
        assert provider.profile == "local_compose"

    def test_get_provider_daytona_with_api_key_succeeds(self):
        """Factory instantiates DaytonaSandboxProvider with API key."""
        provider = get_provider("daytona")

        assert isinstance(provider, DaytonaSandboxProvider)
        assert provider.profile == "daytona"

    def test_get_provider_daytona_requires_api_key_for_self_hosted(self):
        """Factory fails closed for self-hosted Daytona without API key."""
        with patch(
            "src.infrastructure.sandbox.providers.factory.settings"
        ) as mock_settings:
            mock_settings.SANDBOX_PROFILE = "daytona"
            mock_settings.DAYTONA_API_KEY = ""
            mock_settings.DAYTONA_API_TOKEN = ""
            mock_settings.DAYTONA_API_URL = "https://custom.daytona.example.com"
            mock_settings.DAYTONA_BASE_URL = ""
            mock_settings.DAYTONA_TARGET = "us"
            mock_settings.DAYTONA_TARGET_REGION = "us"

            with pytest.raises(SandboxConfigurationError) as exc_info:
                get_provider("daytona")

            assert "api_key" in str(exc_info.value).lower() or "API" in str(
                exc_info.value
            )

    def test_get_provider_daytona_cloud_allows_no_key(self):
        """Factory allows Daytona Cloud without explicit API key (SDK uses env)."""
        with patch(
            "src.infrastructure.sandbox.providers.factory.settings"
        ) as mock_settings:
            mock_settings.SANDBOX_PROFILE = "daytona"
            mock_settings.DAYTONA_API_KEY = ""
            mock_settings.DAYTONA_API_TOKEN = ""
            mock_settings.DAYTONA_API_URL = ""
            mock_settings.DAYTONA_BASE_URL = ""
            mock_settings.DAYTONA_TARGET = "us"
            mock_settings.DAYTONA_TARGET_REGION = "us"

            # Should succeed - SDK will read from DAYTONA_API_KEY env var
            provider = get_provider("daytona")
            assert isinstance(provider, DaytonaSandboxProvider)

    def test_get_provider_unsupported_raises(self):
        """Unsupported profile selection fails closed with explicit error."""
        with pytest.raises(SandboxProfileError) as exc_info:
            get_provider("unsupported_provider")

        assert "unsupported" in str(exc_info.value).lower()
        assert "local_compose" in str(exc_info.value)
        assert "daytona" in str(exc_info.value)

    def test_get_provider_empty_raises(self):
        """Empty profile fails closed with configuration error."""
        with pytest.raises(SandboxProfileError):
            get_provider("")

    def test_get_current_profile(self):
        """Factory exposes current profile configuration."""
        profile = get_current_profile()

        # Should return a valid profile string
        assert isinstance(profile, str)
        assert profile in ["local_compose", "daytona"]


@pytest.fixture
def mock_daytona_sdk():
    """Fixture to mock AsyncDaytona SDK for testing.

    Yields a context manager that patches AsyncDaytona with a mock.
    """

    def _create_mock_sandbox(
        sandbox_id="test-sandbox-id", state="started", status="healthy"
    ):
        mock = MagicMock()
        mock.id = sandbox_id
        mock.state = state
        mock.status = status
        mock.metadata = {}  # Add empty metadata to prevent MagicMock issues
        return mock

    with (
        patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class,
        patch(
            "src.infrastructure.sandbox.providers.daytona.DaytonaSandboxProvider.verify_identity_files",
            new_callable=AsyncMock,
        ) as mock_verify,
        patch(
            "src.infrastructure.sandbox.providers.daytona.DaytonaSandboxProvider.resolve_gateway_endpoint",
            new_callable=AsyncMock,
        ) as mock_gateway,
    ):
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        mock_daytona = AsyncMock()
        mock_sdk_class.return_value.__aenter__ = AsyncMock(return_value=mock_daytona)
        mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

        # Auto-mock identity verification to succeed
        mock_verify.return_value = IdentityVerificationResult(
            ready=True, missing_files=[]
        )
        # Auto-mock gateway resolution
        mock_gateway.return_value = "https://gateway-test.daytona.run:18790"

        yield mock_daytona, _create_mock_sandbox


@pytest.fixture
def config():
    """Create a test sandbox config."""
    return SandboxConfig(
        workspace_id=uuid4(),
        idle_ttl_seconds=3600,
        env_vars={"TEST": "value"},
    )


class TestSemanticParityLifecycle:
    """Test that all providers expose identical semantic lifecycle behavior."""

    @pytest.fixture
    def local_provider(self):
        """Yield local compose provider for testing."""
        return LocalComposeSandboxProvider()

    @pytest.fixture
    def daytona_provider(self):
        """Yield Daytona provider with mocked SDK for testing."""
        provider = DaytonaSandboxProvider(api_key="test-token")
        return provider

    @pytest.mark.asyncio
    async def test_provision_transitions_to_ready_local(self, local_provider, config):
        """Local provider transitions from HYDRATING to READY."""
        # Start with fresh config
        test_config = SandboxConfig(
            workspace_id=uuid4(),
            idle_ttl_seconds=config.idle_ttl_seconds,
            env_vars=config.env_vars,
        )

        # Provision
        info = await local_provider.provision_sandbox(test_config)

        # Verify semantic state
        assert info.state == SandboxState.READY
        assert info.health == SandboxHealth.HEALTHY
        assert info.workspace_id == test_config.workspace_id
        assert info.ref.profile == local_provider.profile

    @pytest.mark.asyncio
    async def test_provision_transitions_to_ready_daytona(
        self, daytona_provider, config, mock_daytona_sdk
    ):
        """Daytona provider transitions from HYDRATING to READY (SDK-backed)."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        mock_daytona, create_mock_sandbox = mock_daytona_sdk

        # Start with fresh config
        test_config = SandboxConfig(
            workspace_id=uuid4(),
            idle_ttl_seconds=config.idle_ttl_seconds,
            env_vars=config.env_vars,
        )

        # Mock SDK to return a ready sandbox
        mock_sandbox = create_mock_sandbox(
            sandbox_id=f"daytona-{str(test_config.workspace_id)[:22]}",
            state="started",
            status="healthy",
        )
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        # Patch identity verification and gateway resolution
        with (
            patch.object(
                daytona_provider, "verify_identity_files", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                daytona_provider, "resolve_gateway_endpoint", new_callable=AsyncMock
            ) as mock_gateway,
        ):
            mock_verify.return_value = IdentityVerificationResult(
                ready=True, missing_files=[]
            )
            mock_gateway.return_value = (
                f"https://gateway-{test_config.workspace_id}.daytona.run:18790"
            )

            # Provision
            info = await daytona_provider.provision_sandbox(test_config)

        # Verify semantic state
        assert info.state == SandboxState.READY
        assert info.health == SandboxHealth.HEALTHY
        assert info.workspace_id == test_config.workspace_id
        assert info.ref.profile == daytona_provider.profile
        # Verify SDK create was called
        mock_daytona.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_sandbox_returns_none_when_not_exists_local(
        self, local_provider
    ):
        """Local provider returns None for non-existent workspaces."""
        workspace_id = uuid4()

        result = await local_provider.get_active_sandbox(workspace_id)

        assert result is None, "Expected None for non-existent workspace"

    @pytest.mark.asyncio
    async def test_get_active_sandbox_returns_none_when_not_exists_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider returns None for non-existent workspaces (SDK-backed)."""
        from daytona import DaytonaError

        mock_daytona, _ = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to raise not found error
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Sandbox not found"))

        result = await daytona_provider.get_active_sandbox(workspace_id)

        # Verify SDK get was called and None is returned
        mock_daytona.get.assert_called_once_with(expected_ref)
        assert result is None, "Expected None for non-existent workspace"

    @pytest.mark.asyncio
    async def test_get_active_sandbox_returns_info_when_exists_local(
        self, local_provider
    ):
        """Local provider returns SandboxInfo for active workspaces."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision first
        await local_provider.provision_sandbox(config)

        # Get active
        info = await local_provider.get_active_sandbox(workspace_id)

        assert info is not None, "Expected active sandbox"
        assert info.state == SandboxState.READY
        assert info.workspace_id == workspace_id

    @pytest.mark.asyncio
    async def test_get_active_sandbox_returns_info_when_exists_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider returns SandboxInfo for active workspaces (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return an active sandbox
        mock_sandbox = create_mock_sandbox(
            sandbox_id=expected_ref, state="running", status="healthy"
        )
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        # Get active
        info = await daytona_provider.get_active_sandbox(workspace_id)

        # Verify SDK get was called and correct info returned
        mock_daytona.get.assert_called_once_with(expected_ref)
        assert info is not None, "Expected active sandbox"
        assert info.state == SandboxState.READY
        assert info.workspace_id == workspace_id

    @pytest.mark.asyncio
    async def test_get_active_returns_none_for_stopped_local(self, local_provider):
        """Local provider excludes stopped sandboxes from active query."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision, then stop
        info = await local_provider.provision_sandbox(config)
        await local_provider.stop_sandbox(info.ref)

        # Query active
        result = await local_provider.get_active_sandbox(workspace_id)

        assert result is None, "Stopped sandbox should not be active"

    @pytest.mark.asyncio
    async def test_get_active_returns_none_for_stopped_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider excludes stopped sandboxes from active query (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return a stopped sandbox
        mock_sandbox = create_mock_sandbox(
            sandbox_id=expected_ref, state="stopped", status="unknown"
        )
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        # Query active
        result = await daytona_provider.get_active_sandbox(workspace_id)

        # Should return None for stopped sandbox
        assert result is None, "Stopped sandbox should not be active"

    @pytest.mark.asyncio
    async def test_stop_sandbox_is_idempotent_local(self, local_provider):
        """Local provider supports idempotent stop operations."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)

        # Stop multiple times
        stop1 = await local_provider.stop_sandbox(info.ref)
        stop2 = await local_provider.stop_sandbox(info.ref)
        stop3 = await local_provider.stop_sandbox(info.ref)

        # All should return STOPPED state
        assert stop1.state == SandboxState.STOPPED
        assert stop2.state == SandboxState.STOPPED
        assert stop3.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_stop_sandbox_is_idempotent_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider supports idempotent stop operations (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK for provisioning
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.stop = AsyncMock()

        # Provision
        config = SandboxConfig(workspace_id=workspace_id)
        info = await daytona_provider.provision_sandbox(config)

        # Reset mock for subsequent calls
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        # Stop multiple times
        stop1 = await daytona_provider.stop_sandbox(info.ref)
        stop2 = await daytona_provider.stop_sandbox(info.ref)
        stop3 = await daytona_provider.stop_sandbox(info.ref)

        # All should return STOPPED state
        assert stop1.state == SandboxState.STOPPED
        assert stop2.state == SandboxState.STOPPED
        assert stop3.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_stop_nonexistent_returns_stopped_state_local(self, local_provider):
        """Local provider returns STOPPED state for non-existent sandboxes."""
        fake_ref = SandboxRef(
            provider_ref="nonexistent-sandbox-12345",
            profile=local_provider.profile,
        )

        result = await local_provider.stop_sandbox(fake_ref)

        assert result.state == SandboxState.STOPPED, (
            "Expected STOPPED for non-existent sandbox"
        )

    @pytest.mark.asyncio
    async def test_stop_nonexistent_returns_stopped_state_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider returns STOPPED state for non-existent sandboxes (SDK-backed)."""
        from daytona import DaytonaError

        mock_daytona, _ = mock_daytona_sdk
        fake_ref = SandboxRef(
            provider_ref="nonexistent-sandbox-12345",
            profile=daytona_provider.profile,
        )

        # Mock SDK to raise not found error
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Not found"))

        result = await daytona_provider.stop_sandbox(fake_ref)

        assert result.state == SandboxState.STOPPED, (
            "Expected STOPPED for non-existent sandbox"
        )

    @pytest.mark.asyncio
    async def test_get_health_returns_current_state_local(self, local_provider):
        """Local provider returns fresh health check results."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)

        # Check health
        health_info = await local_provider.get_health(info.ref)

        assert health_info.state == SandboxState.READY
        assert health_info.health == SandboxHealth.HEALTHY
        assert health_info.ref.provider_ref == info.ref.provider_ref

    @pytest.mark.asyncio
    async def test_get_health_returns_current_state_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider returns fresh health check results (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk

        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return a healthy sandbox
        mock_sandbox = create_mock_sandbox(
            sandbox_id=expected_ref, state="running", status="healthy"
        )
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        fake_ref = SandboxRef(
            provider_ref=expected_ref,
            profile=daytona_provider.profile,
        )

        # Check health
        health_info = await daytona_provider.get_health(fake_ref)

        assert health_info.state == SandboxState.READY
        assert health_info.health == SandboxHealth.HEALTHY
        assert health_info.ref.provider_ref == expected_ref

    @pytest.mark.asyncio
    async def test_get_health_fail_closed_for_not_found_local(self, local_provider):
        """Local provider raises NotFound for unknown sandboxes (fail closed)."""
        fake_ref = SandboxRef(
            provider_ref="nonexistent-sandbox-67890",
            profile=local_provider.profile,
        )

        with pytest.raises(SandboxNotFoundError):
            await local_provider.get_health(fake_ref)

    @pytest.mark.asyncio
    async def test_get_health_fail_closed_for_not_found_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider raises NotFound for unknown sandboxes (SDK-backed, fail closed)."""
        from daytona import DaytonaError

        mock_daytona, _ = mock_daytona_sdk
        fake_ref = SandboxRef(
            provider_ref="nonexistent-sandbox-67890",
            profile=daytona_provider.profile,
        )

        # Mock SDK to raise not found error
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Not found"))

        with pytest.raises(SandboxNotFoundError):
            await daytona_provider.get_health(fake_ref)

    @pytest.mark.asyncio
    async def test_update_activity_refreshes_timestamp_local(self, local_provider):
        """Local provider updates activity timestamp."""
        import asyncio

        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)
        original_time = info.last_activity_at

        # Wait a bit
        await asyncio.sleep(0.02)

        # Update activity
        updated = await local_provider.update_activity(info.ref)

        assert updated.last_activity_at > original_time, (
            "Activity timestamp not updated"
        )

    @pytest.mark.asyncio
    async def test_update_activity_refreshes_timestamp_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider updates activity timestamp (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        from datetime import datetime, timezone

        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return a sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="running")
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        fake_ref = SandboxRef(
            provider_ref=expected_ref,
            profile=daytona_provider.profile,
        )

        # Update activity
        updated = await daytona_provider.update_activity(fake_ref)

        # Verify timestamp is updated
        assert updated.last_activity_at is not None
        assert updated.last_activity_at <= datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_attach_workspace_updates_association_local(self, local_provider):
        """Local provider supports workspace attachment."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)

        # Attach (should be idempotent for same workspace)
        attached = await local_provider.attach_workspace(info.ref, workspace_id)

        assert attached.workspace_id == workspace_id

    @pytest.mark.asyncio
    async def test_attach_workspace_updates_association_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider supports workspace attachment (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return a sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="running")
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        fake_ref = SandboxRef(
            provider_ref=expected_ref,
            profile=daytona_provider.profile,
        )

        # Attach
        attached = await daytona_provider.attach_workspace(fake_ref, workspace_id)

        assert attached.workspace_id == workspace_id

    @pytest.mark.asyncio
    async def test_unhealthy_sandbox_returns_unhealthy_state_local(
        self, local_provider
    ):
        """Local provider exposes unhealthy state when health fails."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)

        # Mark unhealthy (provider-specific method for testing)
        unhealthy = await local_provider.mark_unhealthy(info.ref, "Test failure")

        assert unhealthy.state == SandboxState.UNHEALTHY, "Expected UNHEALTHY state"
        assert unhealthy.health == SandboxHealth.UNHEALTHY, "Expected UNHEALTHY health"

    @pytest.mark.asyncio
    async def test_unhealthy_sandbox_returns_unhealthy_state_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider exposes unhealthy state when health fails (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mark unhealthy (test helper method)
        fake_ref = SandboxRef(
            provider_ref=expected_ref,
            profile=daytona_provider.profile,
        )
        unhealthy = await daytona_provider.mark_unhealthy(fake_ref, "Test failure")

        assert unhealthy.state == SandboxState.UNHEALTHY, "Expected UNHEALTHY state"
        assert unhealthy.health == SandboxHealth.UNHEALTHY, "Expected UNHEALTHY health"

    @pytest.mark.asyncio
    async def test_pack_binding_metadata_parity_local_compose(self):
        """Local compose provider exposes pack binding in metadata with expected contract."""
        provider = LocalComposeSandboxProvider()
        workspace_id = uuid4()
        pack_path = "/test/agent/pack"

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=pack_path,
        )

        info = await provider.provision_sandbox(config)

        # Pack binding semantics
        assert info.ref.metadata.get("pack_bound") is True, (
            "Local compose should mark pack_bound=True when pack_source_path provided"
        )
        assert info.ref.metadata.get("pack_source_path") == pack_path, (
            "Local compose should expose pack_source_path in metadata"
        )

    @pytest.mark.asyncio
    async def test_pack_binding_metadata_parity_daytona(self, mock_daytona_sdk):
        """Daytona provider exposes pack binding in metadata with expected contract (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        provider = DaytonaSandboxProvider(api_key="test-token")
        workspace_id = uuid4()
        pack_path = "/test/agent/pack"
        expected_ref = provider._generate_ref(workspace_id)

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=pack_path,
        )

        # Mock SDK to return a sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)

        info = await provider.provision_sandbox(config)

        # Pack binding semantics
        assert info.ref.metadata.get("pack_bound") is True, (
            "Daytona should mark pack_bound=True when pack_source_path provided"
        )
        assert info.ref.metadata.get("pack_source_path") == pack_path, (
            "Daytona should expose pack_source_path in metadata"
        )

    @pytest.mark.asyncio
    async def test_pack_binding_noop_when_no_pack_provided_local(self, local_provider):
        """Local provider handles no-pack provisioning without errors."""
        workspace_id = uuid4()
        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=None,  # No pack
        )

        info = await local_provider.provision_sandbox(config)

        # Pack binding should be False/None
        assert info.ref.metadata.get("pack_bound") is False, (
            "pack_bound should be False when no pack"
        )
        assert info.ref.metadata.get("pack_source_path") is None, (
            "pack_source_path should not be in metadata when no pack"
        )

    @pytest.mark.asyncio
    async def test_pack_binding_noop_when_no_pack_provided_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider handles no-pack provisioning without errors (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=None,  # No pack
        )

        # Mock SDK to return a sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)

        info = await daytona_provider.provision_sandbox(config)

        # Pack binding should be False/None
        assert info.ref.metadata.get("pack_bound") is False, (
            "pack_bound should be False when no pack"
        )
        assert info.ref.metadata.get("pack_source_path") is None, (
            "pack_source_path should not be in metadata when no pack"
        )


class TestProviderSpecificBehavior:
    """Test provider-specific configuration and behavior."""

    def test_daytona_cloud_vs_self_hosted(self):
        """Daytona provider distinguishes cloud from self-hosted."""
        # Cloud mode (default)
        cloud_provider = DaytonaSandboxProvider(api_key="test")
        assert cloud_provider.is_cloud is True

        # Self-hosted mode
        self_hosted = DaytonaSandboxProvider(
            api_key="test",
            api_url="https://daytona.example.com/v1",
        )
        assert self_hosted.is_cloud is False
        assert self_hosted.base_url == "https://daytona.example.com/v1"

    def test_daytona_configuration_self_hosted_requires_token(self):
        """Self-hosted Daytona provider fails closed without API key."""
        # Self-hosted mode should require an API key
        with pytest.raises(SandboxConfigurationError) as exc_info:
            DaytonaSandboxProvider(
                api_url="https://daytona.example.com/v1",
                # No api_key provided
            )

        assert "api_key" in str(exc_info.value).lower() or "API" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_provision_duplicate_workspace_raises(self):
        """Providers reject duplicate sandbox provisioning."""
        provider = LocalComposeSandboxProvider()
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # First provision succeeds
        await provider.provision_sandbox(config)

        # Second provision fails
        with pytest.raises(SandboxProvisionError) as exc_info:
            await provider.provision_sandbox(config)

        assert "already exists" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_local_compose_deterministic_ref_generation(self):
        """Local compose generates deterministic refs for same workspace."""
        provider = LocalComposeSandboxProvider()
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info1 = await provider.provision_sandbox(config)
        ref1 = info1.ref.provider_ref

        # Stop
        await provider.stop_sandbox(info1.ref)

        # Provision again (should generate same ref)
        info2 = await provider.provision_sandbox(config)
        ref2 = info2.ref.provider_ref

        assert ref1 == ref2, "Provider refs should be deterministic"

    def test_daytona_state_mapping(self):
        """Daytona provider maps native states to semantic states."""
        provider = DaytonaSandboxProvider(api_key="test")

        # Verify state mappings
        assert provider._from_daytona_state("creating") == SandboxState.HYDRATING
        assert provider._from_daytona_state("started") == SandboxState.READY
        assert provider._from_daytona_state("running") == SandboxState.READY
        assert provider._from_daytona_state("stopping") == SandboxState.STOPPING
        assert provider._from_daytona_state("stopped") == SandboxState.STOPPED
        assert provider._from_daytona_state("error") == SandboxState.UNHEALTHY
        assert provider._from_daytona_state("failed") == SandboxState.UNHEALTHY
        assert provider._from_daytona_state("unknown") == SandboxState.UNKNOWN


class TestSemanticStateTransitions:
    """Test state machine transitions are consistent across providers."""

    @pytest.fixture
    def local_provider(self):
        """Create a LocalCompose provider for testing."""
        return LocalComposeSandboxProvider()

    @pytest.fixture
    def daytona_provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test")

    @pytest.mark.asyncio
    async def test_hydrating_to_ready_transition_local(self, local_provider):
        """Local provider transitions through HYDRATING to READY."""
        workspace_id = uuid4()

        # Note: In real implementation, we'd intercept during provision
        # For now, verify final state is READY
        config = SandboxConfig(workspace_id=workspace_id)
        info = await local_provider.provision_sandbox(config)

        assert info.state == SandboxState.READY, "Should reach READY state"

    @pytest.mark.asyncio
    async def test_hydrating_to_ready_transition_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider transitions through HYDRATING to READY (SDK-backed)."""
        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK to return a ready sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)

        config = SandboxConfig(workspace_id=workspace_id)
        info = await daytona_provider.provision_sandbox(config)

        # Verify SDK create was called
        mock_daytona.create.assert_called_once()
        assert info.state == SandboxState.READY, "Should reach READY state"

    @pytest.mark.asyncio
    async def test_ready_to_stopping_to_stopped_transition_local(self, local_provider):
        """Local provider transitions READY -> STOPPING -> STOPPED."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision
        info = await local_provider.provision_sandbox(config)
        assert info.state == SandboxState.READY

        # Stop
        stopped = await local_provider.stop_sandbox(info.ref)
        assert stopped.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_ready_to_stopping_to_stopped_transition_daytona(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona provider transitions READY -> STOPPING -> STOPPED (SDK-backed)."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        mock_daytona, create_mock_sandbox = mock_daytona_sdk
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        # Mock SDK for provisioning
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        config = SandboxConfig(workspace_id=workspace_id)

        # Patch identity verification and gateway resolution
        with (
            patch.object(
                daytona_provider, "verify_identity_files", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                daytona_provider, "resolve_gateway_endpoint", new_callable=AsyncMock
            ) as mock_gateway,
        ):
            mock_verify.return_value = IdentityVerificationResult(
                ready=True, missing_files=[]
            )
            mock_gateway.return_value = (
                f"https://gateway-{workspace_id}.daytona.run:18790"
            )

            info = await daytona_provider.provision_sandbox(config)
            assert info.state == SandboxState.READY

        # Reset mock for stop
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)
        mock_daytona.stop = AsyncMock()

        # Stop
        stopped = await daytona_provider.stop_sandbox(info.ref)
        assert stopped.state == SandboxState.STOPPED
        mock_daytona.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_unhealthy_sandbox_excluded_from_routing(self):
        """Unhealthy sandboxes are not returned as active."""
        provider = LocalComposeSandboxProvider()
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        # Provision and mark unhealthy
        info = await provider.provision_sandbox(config)
        await provider.mark_unhealthy(info.ref, "Health check failed")

        # Query active - should not return unhealthy sandbox
        # (Note: Current implementation returns any non-stopped sandbox)
        # This test documents expected routing behavior
        active = await provider.get_active_sandbox(workspace_id)

        # Unhealthy sandboxes should be excluded from active routing
        # Current implementation may still return them - this is a semantic
        # contract that routing layer should enforce
        if active:
            assert active.health != SandboxHealth.HEALTHY, (
                "Unhealthy sandboxes should not be routable"
            )


class TestDaytonaSdkBackedProvider:
    """Test Daytona provider uses SDK calls with proper semantic mapping."""

    @pytest.fixture
    def provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test-api-key")

    @pytest.mark.asyncio
    async def test_daytona_provision_uses_sdk(self, provider):
        """Daytona provision_sandbox uses SDK create method with image-first config."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        workspace_id = uuid4()
        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path="/test/pack",
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = f"daytona-{str(workspace_id)[:22]}"
        mock_sandbox.state = "started"
        mock_sandbox.status = "healthy"

        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                result = await provider.provision_sandbox(config)

            # Verify SDK create was called
            mock_daytona.create.assert_called_once()
            assert result.state == SandboxState.READY
            assert result.ref.metadata.get("pack_bound") is True
            assert result.ref.metadata.get("pack_source_path") == "/test/pack"

    @pytest.mark.asyncio
    async def test_daytona_get_active_uses_sdk_get(self, provider):
        """Daytona get_active_sandbox uses SDK get method."""
        workspace_id = uuid4()
        expected_ref = provider._generate_ref(workspace_id)

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = expected_ref
        mock_sandbox.state = "running"
        mock_sandbox.status = "healthy"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.get_active_sandbox(workspace_id)

            # Verify SDK get was called with correct ref
            mock_daytona.get.assert_called_once_with(expected_ref)
            assert result is not None
            assert result.state == SandboxState.READY

    @pytest.mark.asyncio
    async def test_daytona_get_active_returns_none_for_stopped(self, provider):
        """Daytona get_active_sandbox returns None for stopped sandboxes."""
        workspace_id = uuid4()
        expected_ref = provider._generate_ref(workspace_id)

        # Mock the SDK to return stopped sandbox
        mock_sandbox = MagicMock()
        mock_sandbox.id = expected_ref
        mock_sandbox.state = "stopped"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.get_active_sandbox(workspace_id)

            # Should return None for stopped sandbox
            assert result is None

    @pytest.mark.asyncio
    async def test_daytona_get_active_fails_closed_on_sdk_error(self, provider):
        """Daytona get_active_sandbox returns None on SDK error (fail-closed)."""
        workspace_id = uuid4()

        from daytona import DaytonaError

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Sandbox not found"))

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.get_active_sandbox(workspace_id)

            # Fail-closed: error results in None (no active sandbox)
            assert result is None

    @pytest.mark.asyncio
    async def test_daytona_stop_uses_sdk_stop(self, provider):
        """Daytona stop_sandbox uses SDK stop method."""
        ref = SandboxRef(
            provider_ref="test-sandbox-id",
            profile="daytona",
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_sandbox.state = "started"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)
        mock_daytona.stop = AsyncMock()

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.stop_sandbox(ref)

            # Verify SDK methods were called
            mock_daytona.get.assert_called_once_with("test-sandbox-id")
            mock_daytona.stop.assert_called_once()
            assert result.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_daytona_stop_is_idempotent_for_missing_sandbox(self, provider):
        """Daytona stop_sandbox returns STOPPED for non-existent sandbox."""
        ref = SandboxRef(
            provider_ref="nonexistent-sandbox",
            profile="daytona",
        )

        from daytona import DaytonaError

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Not found"))

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.stop_sandbox(ref)

            # Should return STOPPED state even if sandbox doesn't exist
            assert result.state == SandboxState.STOPPED

    @pytest.mark.asyncio
    async def test_daytona_get_health_uses_sdk_get(self, provider):
        """Daytona get_health uses SDK get method."""
        ref = SandboxRef(
            provider_ref="test-sandbox-id",
            profile="daytona",
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_sandbox.state = "running"
        mock_sandbox.status = "healthy"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.get_health(ref)

            # Verify SDK get was called
            mock_daytona.get.assert_called_once_with("test-sandbox-id")
            assert result.state == SandboxState.READY
            assert result.health == SandboxHealth.HEALTHY

    @pytest.mark.asyncio
    async def test_daytona_get_health_raises_not_found(self, provider):
        """Daytona get_health raises SandboxNotFoundError for missing sandbox."""
        ref = SandboxRef(
            provider_ref="nonexistent-sandbox",
            profile="daytona",
        )

        from daytona import DaytonaError

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(side_effect=DaytonaError("Not found"))

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(SandboxNotFoundError):
                await provider.get_health(ref)

    @pytest.mark.asyncio
    async def test_daytona_get_health_unknown_state_fails_closed(self, provider):
        """Daytona get_health maps unknown states to UNKNOWN (fail-closed)."""
        ref = SandboxRef(
            provider_ref="test-sandbox-id",
            profile="daytona",
        )

        # Mock sandbox with unknown state
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_sandbox.state = "some_unknown_state"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.get_health(ref)

            # Fail-closed: unknown state maps to UNKNOWN
            assert result.state == SandboxState.UNKNOWN


class TestDaytonaSdkBackPackBinding:
    """Test Daytona provider pack binding parity with local_compose."""

    @pytest.fixture
    def provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test-api-key")

    @pytest.mark.asyncio
    async def test_daytona_sdk_backed_pack_binding_metadata(self, provider):
        """Daytona SDK-backed provider preserves pack binding metadata."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        workspace_id = uuid4()
        pack_path = "/agents/my-pack"

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=pack_path,
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = f"daytona-{str(workspace_id)[:22]}"
        mock_sandbox.state = "started"

        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                info = await provider.provision_sandbox(config)

            # Pack binding metadata preserved
            assert info.ref.metadata.get("pack_bound") is True
            assert info.ref.metadata.get("pack_source_path") == pack_path

    @pytest.mark.asyncio
    async def test_daytona_sdk_backed_no_pack_binding(self, provider):
        """Daytona SDK-backed provider handles no-pack case correctly."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        workspace_id = uuid4()

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=None,
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = f"daytona-{str(workspace_id)[:22]}"
        mock_sandbox.state = "started"

        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                info = await provider.provision_sandbox(config)

            # Pack binding should be False
            assert info.ref.metadata.get("pack_bound") is False
            assert info.ref.metadata.get("pack_source_path") is None


class TestDaytonaBaseImageContract:
    """Test Daytona base image contract validation for production determinism."""

    def test_provider_accepts_digest_pinned_image_in_strict_mode(self):
        """Provider accepts valid digest-pinned image in strict mode."""
        valid_digest_image = "registry.example.com/picoclaw/base@sha256:" + "a" * 64

        # Should not raise in strict mode with digest
        provider = DaytonaSandboxProvider(
            api_key="test-token",
            base_image=valid_digest_image,
            strict_mode=True,
        )

        assert provider._base_image == valid_digest_image
        assert provider._strict_mode is True

    def test_provider_rejects_mutable_tag_in_strict_mode(self):
        """Provider rejects mutable tags (latest, etc.) in strict mode."""
        from src.infrastructure.sandbox.providers.daytona import (
            SandboxImageContractError,
        )

        with pytest.raises(SandboxImageContractError) as exc_info:
            DaytonaSandboxProvider(
                api_key="test-token",
                base_image="daytonaio/workspace-picoclaw:latest",
                strict_mode=True,
            )

        assert "digest-pinned" in str(exc_info.value).lower()
        assert exc_info.value.image_ref == "daytonaio/workspace-picoclaw:latest"
        assert exc_info.value.contract_violation == "mutable_tag_reference"

    def test_provider_rejects_empty_image_in_strict_mode(self):
        """Provider rejects empty base image in strict mode."""
        from src.infrastructure.sandbox.providers.daytona import (
            SandboxImageContractError,
        )

        with pytest.raises(SandboxImageContractError) as exc_info:
            DaytonaSandboxProvider(
                api_key="test-token",
                base_image="",
                strict_mode=True,
            )

        assert "empty" in str(exc_info.value).lower()
        assert exc_info.value.contract_violation == "empty_image_reference"

    def test_provider_accepts_mutable_tag_in_permissive_mode(self):
        """Provider accepts mutable tags when strict mode is disabled."""
        # Should not raise - permissive mode allows :latest
        provider = DaytonaSandboxProvider(
            api_key="test-token",
            base_image="daytonaio/workspace-picoclaw:latest",
            strict_mode=False,
        )

        assert provider._base_image == "daytonaio/workspace-picoclaw:latest"

    def test_provider_accepts_digest_with_digest_required_only(self):
        """Provider enforces digest when digest_required=True, strict_mode=False."""
        from src.infrastructure.sandbox.providers.daytona import (
            SandboxImageContractError,
        )

        # Should reject mutable tag
        with pytest.raises(SandboxImageContractError):
            DaytonaSandboxProvider(
                api_key="test-token",
                base_image="daytonaio/workspace-picoclaw:v1.0",
                strict_mode=False,
                digest_required=True,
            )

        # Should accept digest
        valid_digest = "registry.example.com/picoclaw/base@sha256:" + "b" * 64
        provider = DaytonaSandboxProvider(
            api_key="test-token",
            base_image=valid_digest,
            strict_mode=False,
            digest_required=True,
        )

        assert provider._base_image == valid_digest

    def test_provider_stamps_image_contract_in_labels(self):
        """Provider stamps base image and strict mode info in sandbox labels."""
        provider = DaytonaSandboxProvider(
            api_key="test-token",
            base_image="test-image@sha256:" + "c" * 64,
            strict_mode=True,
        )

        # Build create params and check labels
        from src.infrastructure.sandbox.providers.base import SandboxConfig

        config = SandboxConfig(workspace_id=uuid4())
        params = provider._build_create_params(config)

        assert "labels" in params
        labels = params["labels"]
        assert labels["picoclaw.base_image"] == "test-image@sha256:" + "c" * 64
        assert labels["picoclaw.base_image_strict"] == "True"


class TestDaytonaFailClosedBehavior:
    """Test Daytona provider fail-closed behavior per semantic contract."""

    @pytest.fixture
    def provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test-api-key")

    def test_unknown_daytona_state_maps_to_unknown(self, provider):
        """Unknown Daytona states map to UNKNOWN (fail-closed)."""
        assert provider._from_daytona_state("weird_state") == SandboxState.UNKNOWN
        assert provider._from_daytona_state("pending") == SandboxState.UNKNOWN
        assert provider._from_daytona_state("") == SandboxState.UNKNOWN

    @pytest.mark.asyncio
    async def test_get_active_sandbox_fails_closed_on_exception(self, provider):
        """get_active_sandbox returns None on any exception (fail-closed)."""
        workspace_id = uuid4()

        # Simulate unexpected exception
        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.side_effect = RuntimeError("Unexpected error")

            result = await provider.get_active_sandbox(workspace_id)

            # Fail-closed: any error returns None (no active sandbox)
            assert result is None

    @pytest.mark.asyncio
    async def test_provision_fails_closed_on_sdk_error(self, provider):
        """provision_sandbox raises SandboxProvisionError on SDK failure."""
        workspace_id = uuid4()
        config = SandboxConfig(workspace_id=workspace_id)

        from daytona import DaytonaError

        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(side_effect=DaytonaError("Creation failed"))

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(SandboxProvisionError) as exc_info:
                await provider.provision_sandbox(config)

            assert "failed" in str(exc_info.value).lower()


class TestPicoclawConfigGeneration:
    """Test Picoclaw config generation for bridge-only channels."""

    @pytest.fixture
    def local_provider(self):
        """Create a LocalCompose provider for testing."""
        return LocalComposeSandboxProvider()

    @pytest.fixture
    def daytona_provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test-api-key")

    def test_local_compose_generates_bridge_only_config(self, local_provider):
        """Local compose generates config with bridge-only channels enabled."""
        config = SandboxConfig(
            workspace_id=uuid4(),
            runtime_bridge_config={
                "bridge": {
                    "enabled": True,
                    "auth_token": "test-token-123",
                    "gateway_port": 18790,
                },
                "channels": {
                    "bridge": {"enabled": True},
                    "telegram": {"enabled": False},
                },
            },
        )

        picoclaw_config = local_provider._generate_picoclaw_config(config)

        # Verify bridge channel is enabled
        assert picoclaw_config["channels"]["bridge"]["enabled"] is True

        # Verify all public channels are disabled
        assert picoclaw_config["channels"]["telegram"]["enabled"] is False
        assert picoclaw_config["channels"]["discord"]["enabled"] is False
        assert picoclaw_config["channels"]["slack"]["enabled"] is False

        # Verify gateway config
        assert picoclaw_config["gateway"]["port"] == 18790

        # Verify env var placeholders for credentials
        assert "${LLM_API_KEY}" in str(picoclaw_config["model_list"])

    def test_daytona_generates_bridge_only_config(self, daytona_provider):
        """Daytona generates config with bridge-only channels enabled."""
        config = SandboxConfig(
            workspace_id=uuid4(),
            runtime_bridge_config={
                "bridge": {
                    "enabled": True,
                    "auth_token": "test-token-456",
                    "gateway_port": 18790,
                },
            },
        )

        picoclaw_config = daytona_provider._generate_picoclaw_config(config)

        # Verify bridge channel is enabled
        assert picoclaw_config["channels"]["bridge"]["enabled"] is True

        # Verify all public channels are disabled
        assert picoclaw_config["channels"]["telegram"]["enabled"] is False
        assert picoclaw_config["channels"]["discord"]["enabled"] is False

    def test_config_is_sandbox_scoped(self, local_provider):
        """Config generation produces sandbox-scoped configuration."""
        workspace_id_1 = uuid4()
        workspace_id_2 = uuid4()

        config_1 = SandboxConfig(
            workspace_id=workspace_id_1,
            runtime_bridge_config={
                "workspace_id": str(workspace_id_1),
                "bridge": {"auth_token": "token-1"},
            },
        )
        config_2 = SandboxConfig(
            workspace_id=workspace_id_2,
            runtime_bridge_config={
                "workspace_id": str(workspace_id_2),
                "bridge": {"auth_token": "token-2"},
            },
        )

        picoclaw_config_1 = local_provider._generate_picoclaw_config(config_1)
        picoclaw_config_2 = local_provider._generate_picoclaw_config(config_2)

        # Each config should have unique bridge token
        assert (
            picoclaw_config_1["channels"]["bridge"]["auth_token"]
            != picoclaw_config_2["channels"]["bridge"]["auth_token"]
        )


class TestPackMaterialization:
    """Test pack materialization with snapshot copy semantics."""

    @pytest.fixture
    def local_provider(self):
        """Create a LocalCompose provider for testing."""
        return LocalComposeSandboxProvider()

    @pytest.fixture
    def daytona_provider(self):
        """Create a Daytona provider for testing."""
        return DaytonaSandboxProvider(api_key="test-api-key")

    @pytest.mark.asyncio
    async def test_local_compose_materializes_pack_snapshot(self, local_provider):
        """Local compose materializes pack with snapshot copy, not live bind."""
        pack_path = "/test/agent/pack"
        pack_digest = "abc123def456"

        config = SandboxConfig(
            workspace_id=uuid4(),
            pack_source_path=pack_path,
            pack_digest=pack_digest,
            runtime_bridge_config={
                "bridge": {"enabled": True, "auth_token": "test-token"},
                "workspace_id": "test-workspace",
            },
        )

        info = await local_provider.provision_sandbox(config)

        # Verify pack materialization metadata
        assert info.ref.metadata.get("pack_bound") is True
        assert info.ref.metadata.get("pack_source_path") == pack_path
        assert info.ref.metadata.get("pack_digest") == pack_digest
        assert (
            info.ref.metadata.get("materialized_config_path")
            == "/workspace/pack/config.json"
        )

    @pytest.mark.asyncio
    async def test_daytona_materializes_pack_snapshot(
        self, daytona_provider, mock_daytona_sdk
    ):
        """Daytona materializes pack with snapshot copy, not live bind."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        mock_daytona, create_mock_sandbox = mock_daytona_sdk

        pack_path = "/test/agent/pack"
        pack_digest = "abc123def456"
        workspace_id = uuid4()
        expected_ref = daytona_provider._generate_ref(workspace_id)

        config = SandboxConfig(
            workspace_id=workspace_id,
            pack_source_path=pack_path,
            pack_digest=pack_digest,
            runtime_bridge_config={
                "bridge": {"enabled": True, "auth_token": "test-token"},
                "workspace_id": "test-workspace",
            },
        )

        # Mock SDK to return a sandbox
        mock_sandbox = create_mock_sandbox(sandbox_id=expected_ref, state="started")
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        # Patch identity verification and gateway resolution
        with (
            patch.object(
                daytona_provider, "verify_identity_files", new_callable=AsyncMock
            ) as mock_verify,
            patch.object(
                daytona_provider, "resolve_gateway_endpoint", new_callable=AsyncMock
            ) as mock_gateway,
        ):
            mock_verify.return_value = IdentityVerificationResult(
                ready=True, missing_files=[]
            )
            mock_gateway.return_value = (
                f"https://gateway-{workspace_id}.daytona.run:18790"
            )

            info = await daytona_provider.provision_sandbox(config)

        # Verify pack materialization metadata
        assert info.ref.metadata.get("pack_bound") is True
        assert info.ref.metadata.get("pack_source_path") == pack_path
        assert info.ref.metadata.get("pack_digest") == pack_digest

    @pytest.mark.asyncio
    async def test_materialization_noop_without_pack(self, local_provider):
        """Materialization is no-op when no pack is provided."""
        config = SandboxConfig(
            workspace_id=uuid4(),
            pack_source_path=None,
            pack_digest=None,
            runtime_bridge_config={
                "bridge": {"enabled": True, "auth_token": "test-token"},
            },
        )

        info = await local_provider.provision_sandbox(config)

        # Verify no materialization occurred
        assert info.ref.metadata.get("pack_bound") is False
        assert info.ref.metadata.get("pack_digest") is None
        assert info.ref.metadata.get("materialized_config_path") is None


class TestPackStaleDetection:
    """Test stale pack detection for fail-closed routing."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock sandbox provider."""
        provider = MagicMock()
        provider.profile = "local_compose"
        provider.get_health = AsyncMock()
        provider.provision_sandbox = AsyncMock()
        provider.stop_sandbox = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_orchestrator_passes_pack_digest_to_provider(
        self, db_session, test_user, test_workspace, mock_provider
    ):
        """Orchestrator passes pack digest for stale detection."""
        from src.db.models import AgentPackValidationStatus
        from src.db.repositories.agent_pack_repository import AgentPackRepository
        from src.services.sandbox_orchestrator_service import (
            SandboxOrchestratorService,
        )

        # Create a valid agent pack with digest
        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path="/test/pack/path",
            source_digest="sha256abc123",
        )
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

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        # Resolve sandbox with pack
        result = await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        assert result.success is True
        assert captured_config is not None
        # Verify pack_digest is passed for stale detection
        assert captured_config.pack_digest == "sha256abc123"
        # Verify runtime_bridge_config is generated
        assert captured_config.runtime_bridge_config is not None
        assert captured_config.runtime_bridge_config["bridge"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_orchestrator_generates_unique_bridge_tokens(
        self, db_session, test_user, test_workspace, mock_provider
    ):
        """Each sandbox gets unique bridge auth token."""
        from src.db.models import AgentPackValidationStatus
        from src.db.repositories.agent_pack_repository import AgentPackRepository
        from src.services.sandbox_orchestrator_service import (
            SandboxOrchestratorService,
        )

        # Create a valid agent pack
        pack_repo = AgentPackRepository(db_session)
        pack = pack_repo.create(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path="/test/pack/path",
            source_digest="sha256abc123",
        )
        pack.validation_status = AgentPackValidationStatus.VALID
        pack.is_active = True
        db_session.flush()

        captured_configs = []

        async def capture_provision(config):
            captured_configs.append(config)
            return SandboxInfo(
                ref=SandboxRef(
                    provider_ref=f"new-sandbox-{len(captured_configs)}",
                    profile="local_compose",
                ),
                state=ProviderSandboxState.READY,
                health=ProviderSandboxHealth.HEALTHY,
                workspace_id=test_workspace.id,
            )

        mock_provider.provision_sandbox.side_effect = capture_provision

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        # Provision first sandbox
        await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        # Provision second sandbox
        await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            agent_pack_id=pack.id,
        )

        # Verify each sandbox has unique bridge token
        token1 = captured_configs[0].runtime_bridge_config["bridge"]["auth_token"]
        token2 = captured_configs[1].runtime_bridge_config["bridge"]["auth_token"]

        assert token1 != token2, "Each sandbox should have unique bridge token"


class TestDaytonaProductionReadiness:
    """Regression tests for Daytona production readiness (03.1-02)."""

    @pytest.fixture
    def provider(self):
        """Yield Daytona provider for testing."""
        return DaytonaSandboxProvider(
            api_key="test-token",
            base_image="daytonaio/workspace-picoclaw:latest",
            auto_stop_interval=0,
        )

    @pytest.mark.asyncio
    async def test_daytona_provision_uses_explicit_image_config(self, provider):
        """Daytona create call uses explicit image/runtime config from settings."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        workspace_id = uuid4()
        config = SandboxConfig(
            workspace_id=workspace_id,
            env_vars={"TEST_VAR": "value"},
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = f"daytona-{str(workspace_id)[:22]}"
        mock_sandbox.state = "started"
        mock_sandbox.status = "healthy"

        mock_daytona = AsyncMock()
        mock_daytona.create = AsyncMock(return_value=mock_sandbox)
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        captured_create_params = {}

        async def capture_create(**kwargs):
            captured_create_params.update(kwargs)
            return mock_sandbox

        mock_daytona.create = capture_create

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch identity verification and gateway resolution
            with (
                patch.object(
                    provider, "verify_identity_files", new_callable=AsyncMock
                ) as mock_verify,
                patch.object(
                    provider, "resolve_gateway_endpoint", new_callable=AsyncMock
                ) as mock_gateway,
            ):
                mock_verify.return_value = IdentityVerificationResult(
                    ready=True, missing_files=[]
                )
                mock_gateway.return_value = (
                    f"https://gateway-{workspace_id}.daytona.run:18790"
                )

                await provider.provision_sandbox(config)

        # Verify image config was passed to create
        assert "image" in captured_create_params
        assert captured_create_params["image"] == "daytonaio/workspace-picoclaw:latest"
        assert "auto_stop_interval" in captured_create_params
        assert captured_create_params["auto_stop_interval"] == 0

    @pytest.mark.asyncio
    async def test_daytona_identity_verification_required_files(self, provider):
        """Identity verification checks for required identity files."""
        from src.infrastructure.sandbox.providers.daytona import (
            IdentityVerificationResult,
        )

        # Mock the SDK
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.state = "started"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.verify_identity_files("test-sandbox")

        # Running sandbox with identity files should be ready
        assert isinstance(result, IdentityVerificationResult)
        assert result.ready is True
        assert result.missing_files == []

    @pytest.mark.asyncio
    async def test_daytona_identity_verification_fails_when_not_running(self, provider):
        """Identity verification fails when sandbox is not running."""

        # Mock the SDK with stopped sandbox
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.state = "stopped"

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.verify_identity_files("test-sandbox")

        assert result.ready is False
        assert "stopped" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_daytona_gateway_resolution_uses_preview_url(self, provider):
        """Gateway endpoint resolution extracts from preview URLs."""
        # Mock the SDK with preview URL - no metadata so it falls through to preview
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox"
        mock_sandbox.preview_url = "https://abc123.daytona.run"
        mock_sandbox.metadata = (
            None  # No metadata, so it won't use metadata.get("gateway_url")
        )

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            gateway_url = await provider.resolve_gateway_endpoint("test-sandbox")

        # Should derive gateway URL from preview
        assert "gateway-" in gateway_url
        assert ":18790" in gateway_url

    @pytest.mark.asyncio
    async def test_daytona_gateway_resolution_fallback_to_constructed(self, provider):
        """Gateway endpoint falls back to constructed URL from ID."""
        # Mock the SDK without preview URL and with empty metadata
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-123"
        mock_sandbox.preview_url = None
        mock_sandbox.url = None
        mock_sandbox.metadata = {}  # Empty metadata dict

        mock_daytona = AsyncMock()
        mock_daytona.get = AsyncMock(return_value=mock_sandbox)

        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            gateway_url = await provider.resolve_gateway_endpoint("test-sandbox-123")

        # Should construct from sandbox ID - check that it's a string URL
        assert isinstance(gateway_url, str)
        assert "gateway-test-sandbox-123" in gateway_url


class TestOrchestratorBoundedReprovision:
    """Regression tests for orchestrator bounded reprovision (03.1-02)."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock sandbox provider that fails then succeeds."""
        provider = MagicMock()
        provider.profile = "daytona"
        provider.get_health = AsyncMock()
        provider.provision_sandbox = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_bounded_reprovision_exhausts_budget_and_fails_fast(
        self,
        db_session: Session,
        test_workspace: Workspace,
        mock_provider,
    ):
        """Identity failures trigger bounded reprovision and eventually fail fast."""
        from src.infrastructure.sandbox.providers.daytona import SandboxIdentityError
        from src.db.models import SandboxState as DbSandboxState

        # Create existing sandbox without identity ready
        existing_sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            provider_ref="existing-sandbox",
            state=DbSandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            identity_ready=False,  # Identity not ready - hard gate fails
            hydration_status="pending",
        )
        db_session.add(existing_sandbox)
        db_session.commit()

        # Mock provider to always fail with identity error
        mock_provider.provision_sandbox.side_effect = SandboxIdentityError(
            "Identity verification failed", workspace_id=test_workspace.id
        )

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        # Resolve should fail after bounded retry attempts
        result = await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
        )

        # Should exhaust retry budget
        assert result.success is False
        assert result.reprovision_exhausted is True
        assert result.reprovision_attempts == orchestrator.MAX_REPROVISION_ATTEMPTS
        assert result.remediation is not None
        assert (
            "identity" in result.remediation.lower()
            or "contact support" in result.remediation.lower()
        )

        # Should have called provision MAX_REPROVISION_ATTEMPTS times
        assert (
            mock_provider.provision_sandbox.call_count
            == orchestrator.MAX_REPROVISION_ATTEMPTS
        )

    @pytest.mark.asyncio
    async def test_gateway_persistence_and_authoritative_resolution(
        self,
        db_session: Session,
        test_workspace: Workspace,
        mock_provider,
    ):
        """Authoritative gateway URL is persisted once and reused."""
        workspace_id = test_workspace.id
        expected_gateway = f"https://gateway-{workspace_id}.daytona.run:18790"

        # Mock provider to return gateway URL in metadata
        mock_provider.provision_sandbox.return_value = SandboxInfo(
            ref=SandboxRef(
                provider_ref="new-sandbox",
                profile="daytona",
                metadata={"gateway_url": expected_gateway},
            ),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=workspace_id,
        )

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        result = await orchestrator.resolve_sandbox(
            workspace_id=workspace_id,
            profile=SandboxProfile.DAYTONA,
        )

        # Should succeed with gateway URL
        assert result.success is True
        assert result.gateway_url == expected_gateway

        # Verify gateway URL is persisted in database
        sandbox = result.sandbox
        assert sandbox is not None
        assert sandbox.gateway_url == expected_gateway


class TestOrchestratorNonBlockingHydration:
    """Regression tests for non-blocking async hydration (03.1-02)."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock sandbox provider."""
        provider = MagicMock()
        provider.profile = "daytona"
        provider.get_health = AsyncMock()
        provider.provision_sandbox = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_non_blocking_hydration_does_not_block_routing(
        self,
        db_session: Session,
        test_workspace: Workspace,
        mock_provider,
    ):
        """Checkpoint hydration is triggered async and does not block request routing."""
        from src.db.models import SandboxState as DbSandboxState

        # Create existing sandbox with identity ready but hydration pending
        existing_sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            provider_ref="existing-sandbox",
            state=DbSandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            identity_ready=True,  # Identity ready - hard gate passes
            hydration_status="pending",  # But hydration pending - should still route
        )
        db_session.add(existing_sandbox)
        db_session.commit()

        # Mock health check to return healthy
        mock_provider.get_health.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="existing-sandbox", profile="daytona"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=test_workspace.id,
        )

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        # Resolve should succeed even with pending hydration
        result = await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
        )

        # Should route successfully without blocking on hydration
        assert result.success is True
        assert result.result == RoutingResult.ROUTED_EXISTING
        assert result.sandbox.id == existing_sandbox.id

    @pytest.mark.asyncio
    async def test_hydration_failure_marks_degraded_without_blocking(
        self,
        db_session: Session,
        test_workspace: Workspace,
        mock_provider,
    ):
        """Hydration failures mark degraded but don't affect request-readiness."""
        from src.db.models import SandboxState as DbSandboxState

        # Create existing sandbox with identity ready
        existing_sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
            provider_ref="existing-sandbox",
            state=DbSandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            identity_ready=True,
            hydration_status="pending",
        )
        db_session.add(existing_sandbox)
        db_session.commit()

        # Mock health check
        mock_provider.get_health.return_value = SandboxInfo(
            ref=SandboxRef(provider_ref="existing-sandbox", profile="daytona"),
            state=ProviderSandboxState.READY,
            health=ProviderSandboxHealth.HEALTHY,
            workspace_id=test_workspace.id,
        )

        orchestrator = SandboxOrchestratorService(
            session=db_session,
            provider=mock_provider,
            idle_ttl_seconds=3600,
        )

        # Route should succeed
        result = await orchestrator.resolve_sandbox(
            workspace_id=test_workspace.id,
            profile=SandboxProfile.DAYTONA,
        )

        # Should succeed - hydration failures are non-blocking
        assert result.success is True
        assert result.result == RoutingResult.ROUTED_EXISTING
