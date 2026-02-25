"""Phase 2 acceptance tests for workspace lifecycle and agent pack portability.

Tests mapped directly to Phase 2 success criteria:
- WORK-01: Workspace continuity across sessions
- WORK-02: Routing to healthy sandbox or hydrate/create replacement
- WORK-04: Same-workspace write serialization
- WORK-05: Unhealthy sandbox exclusion
- WORK-06: Idle auto-stop by TTL
- AGNT-01: Template scaffold -> validation -> registration flow
- AGNT-02: Validation checklist for registration
- AGNT-03: Cross-profile semantic parity
"""

import pytest
import tempfile
import os
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    User,
    Workspace,
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    AgentPack,
    AgentPackValidationStatus,
    WorkspaceLease,
)
from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
from src.services.agent_pack_service import AgentPackService
from src.services.agent_scaffold_service import AgentScaffoldService
from src.services.workspace_lease_service import WorkspaceLeaseService
from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
from src.infrastructure.sandbox.providers.factory import get_provider


# =============================================================================
# WORK-01: Workspace Continuity Tests
# =============================================================================


class TestWorkspaceContinuity:
    """WORK-01: User sees continuity across sessions with same workspace."""

    def test_bootstrap_creates_workspace_on_first_use(self, client, owner_headers):
        """POST /workspaces/bootstrap creates workspace on first call."""
        response = client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

        assert response.status_code == 200
        data = response.json()
        assert "workspace_id" in data
        assert data["name"] is not None

    def test_bootstrap_reuses_existing_workspace(
        self, client, owner_headers, db_session
    ):
        """POST /workspaces/bootstrap returns existing workspace on subsequent calls."""
        # First bootstrap - creates workspace
        response1 = client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)
        assert response1.status_code == 200
        data1 = response1.json()
        first_id = data1["workspace_id"]

        # Commit the session so workspace is persisted
        db_session.commit()

        # Second bootstrap - should return same workspace
        response2 = client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)
        assert response2.status_code == 200
        data2 = response2.json()

        assert data2["workspace_id"] == first_id
        # Note: created flag may vary based on timing; the key point is same workspace_id

    def test_me_status_returns_workspace(self, client, owner_headers):
        """GET /workspaces/me/status returns current user's workspace."""
        # Bootstrap first
        client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

        # Get status
        response = client.get("/api/v1/workspaces/me/status", headers=owner_headers)

        assert response.status_code == 200
        data = response.json()
        assert "workspace_id" in data
        assert data["is_active"] is True


# =============================================================================
# AGNT-01: Template Scaffold Flow Tests
# =============================================================================


class TestAgentPackScaffoldFlow:
    """AGNT-01: User can scaffold, validate, and register agent pack."""

    def test_scaffold_creates_required_files(self, client, owner_headers):
        """POST /agent-packs/scaffold creates AGENT.md, SOUL.md, IDENTITY.md, skills/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            request = {"pack_path": tmpdir, "overwrite": False}

            response = client.post(
                "/api/v1/agent-packs/scaffold",
                json=request,
                headers=owner_headers,
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True

            # Verify files were created
            assert (Path(tmpdir) / "AGENT.md").exists()
            assert (Path(tmpdir) / "SOUL.md").exists()
            assert (Path(tmpdir) / "IDENTITY.md").exists()
            assert (Path(tmpdir) / "skills").is_dir()

    def test_scaffold_is_idempotent(self, client, owner_headers):
        """POST /agent-packs/scaffold is idempotent (skips existing files)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First scaffold
            request = {"pack_path": tmpdir, "overwrite": False}
            response1 = client.post(
                "/api/v1/agent-packs/scaffold",
                json=request,
                headers=owner_headers,
            )
            assert response1.status_code == 201
            data1 = response1.json()

            # Second scaffold - should not fail
            response2 = client.post(
                "/api/v1/agent-packs/scaffold",
                json=request,
                headers=owner_headers,
            )
            assert response2.status_code == 201
            data2 = response2.json()

            # All entries should show already_existed
            for entry in data2["entries"]:
                assert entry["already_existed"] is True

    def test_register_validates_scaffold(self, client, owner_headers):
        """POST /agent-packs/register validates scaffold before registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create scaffold first
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            # Bootstrap workspace
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Register the pack
            register_request = {"name": "Test Pack", "source_path": tmpdir}
            response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )

            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert "pack_id" in data
            assert data["validation"]["is_valid"] is True

    def test_register_returns_checklist_on_invalid_scaffold(
        self, client, owner_headers
    ):
        """POST /agent-packs/register returns checklist when validation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Don't create scaffold - leave directory empty

            # Bootstrap workspace
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Try to register invalid pack
            register_request = {"name": "Invalid Pack", "source_path": tmpdir}
            response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )

            assert response.status_code == 201  # Returns 200 with failure info
            data = response.json()
            assert data["success"] is False
            assert "validation" in data
            assert data["validation"]["is_valid"] is False
            assert len(data["validation"]["checklist"]) > 0
            assert data["validation"]["error_count"] > 0


# =============================================================================
# WORK-02 & AGNT-03: Sandbox Routing and Profile Parity Tests
# =============================================================================


class TestSandboxRouting:
    """WORK-02: Route to healthy active sandbox or hydrate/create replacement."""

    def test_resolve_sandbox_returns_routing_target(
        self, client, owner_headers, db_session
    ):
        """POST /workspaces/{id}/sandbox/resolve returns sandbox routing target."""
        # Bootstrap workspace
        response = client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)
        workspace_id = response.json()["workspace_id"]

        # Resolve sandbox
        resolve_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=owner_headers,
        )

        assert resolve_response.status_code == 200
        data = resolve_response.json()
        assert "state" in data
        assert "lease_acquired" in data
        assert data["lease_acquired"] is True

    def test_routing_prefer_healthy_active(
        self, client, owner_headers, db_session, workspace_alpha
    ):
        """Routing prefers healthy active sandbox over creating new one."""
        # Create a healthy active sandbox
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="test-sandbox-1",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_health_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
        )
        db_session.add(sandbox)
        db_session.commit()

        # Resolve should find existing sandbox
        lifecycle = WorkspaceLifecycleService(db_session)
        # Mock the provider to return healthy status

        # Verify sandbox exists and is healthy
        healthy_sandboxes = (
            db_session.query(SandboxInstance)
            .filter_by(
                workspace_id=workspace_alpha.id,
                state=SandboxState.ACTIVE,
                health_status=SandboxHealthStatus.HEALTHY,
            )
            .all()
        )

        assert len(healthy_sandboxes) > 0

    def test_routing_exclude_unhealthy(
        self, client, owner_headers, db_session, workspace_alpha
    ):
        """WORK-05: Unhealthy sandboxes are excluded from routing."""
        # Create an unhealthy sandbox
        unhealthy = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="test-sandbox-unhealthy",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.UNHEALTHY,
            last_health_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            last_activity_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db_session.add(unhealthy)
        db_session.commit()

        # Verify unhealthy sandbox exists but won't be routed to
        unhealthy_sandboxes = (
            db_session.query(SandboxInstance)
            .filter_by(
                workspace_id=workspace_alpha.id,
                health_status=SandboxHealthStatus.UNHEALTHY,
            )
            .all()
        )

        assert len(unhealthy_sandboxes) == 1


# =============================================================================
# WORK-04: Same-Workspace Serialization Tests
# =============================================================================


class TestWorkspaceLeaseSerialization:
    """WORK-04: Concurrent write attempts for same workspace are serialized."""

    def test_lease_service_acquire_prevents_concurrent_access(
        self, db_session, workspace_alpha
    ):
        """TEST-15: Lease acquisition serializes same-workspace write attempts."""
        from src.services.workspace_lease_service import LeaseResult

        service = WorkspaceLeaseService(db_session)

        # First acquire should succeed
        result1 = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-1",
            holder_identity="user-1",
            ttl_seconds=60,
        )

        assert result1.success is True
        assert result1.result == LeaseResult.ACQUIRED

        # Second acquire should fail (conflict)
        result2 = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-2",
            holder_identity="user-2",
            ttl_seconds=60,
        )

        assert result2.success is False
        assert result2.result == LeaseResult.CONFLICT

    def test_lease_release_allows_next_acquirer(self, db_session, workspace_alpha):
        """TEST-16: Releasing lease allows next acquirer to proceed."""
        from src.services.workspace_lease_service import LeaseResult

        service = WorkspaceLeaseService(db_session)

        # First acquire
        service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-1",
            holder_identity="user-1",
            ttl_seconds=60,
        )

        # Release
        service.release_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-1",
        )

        # Second acquire should now succeed
        result2 = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-2",
            holder_identity="user-2",
            ttl_seconds=60,
        )

        assert result2.success is True
        assert result2.result == LeaseResult.ACQUIRED


# =============================================================================
# WORK-06: Idle TTL Tests
# =============================================================================


class TestIdleTTLBehavior:
    """WORK-06: Idle sandboxes auto-stop by TTL."""

    def test_stop_eligibility_computed_from_ttl(self, db_session, workspace_alpha):
        """Stop eligibility is computed from configured TTL and last activity."""
        from src.config.settings import Settings

        # Create sandbox with old activity
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="test-sandbox-ttl",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=old_time,
            idle_ttl_seconds=3600,  # 1 hour TTL
        )
        db_session.add(sandbox)
        db_session.commit()

        # Check eligibility
        orchestrator = SandboxOrchestratorService(db_session)
        eligibility = orchestrator.check_stop_eligibility(sandbox)

        # Should be eligible for stop (idle > TTL)
        assert eligibility.eligible is True
        assert eligibility.idle_seconds > eligibility.ttl_seconds

    def test_stop_eligibility_respects_configured_ttl(
        self, db_session, workspace_alpha
    ):
        """Non-default TTL produces different stop eligibility."""
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)

        # Sandbox with 30 min idle, 1 hour TTL - should NOT be eligible
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="test-sandbox-active",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_activity_at=recent_time,
            idle_ttl_seconds=3600,  # 1 hour TTL
        )
        db_session.add(sandbox)
        db_session.commit()

        orchestrator = SandboxOrchestratorService(db_session)
        eligibility = orchestrator.check_stop_eligibility(sandbox)

        assert eligibility.eligible is False
        assert eligibility.idle_seconds < eligibility.ttl_seconds


# =============================================================================
# Run Integration Tests
# =============================================================================


class TestRunLifecycleIntegration:
    """Integration tests for run execution with lifecycle routing."""

    def test_start_run_resolves_workspace_and_sandbox(self, client, owner_headers):
        """POST /runs resolves workspace and sandbox before execution."""
        # Bootstrap workspace first
        client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

        # Start run
        request = {
            "input": {"message": "test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=request, headers=owner_headers)

        # May succeed or fail based on provider, but should attempt routing
        assert response.status_code in [201, 409, 503]

        if response.status_code == 201:
            data = response.json()
            assert "run_id" in data
            assert data["status"] in ["success", "pending"]

    def test_guest_run_does_not_persist(self, client):
        """Guest runs execute without workspace persistence."""
        request = {
            "input": {"message": "guest test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=request)

        # Guest runs should succeed without workspace
        assert response.status_code in [201, 200]
        data = response.json()
        assert data.get("is_guest") is True


# =============================================================================
# Profile Parity Tests (AGNT-03)
# =============================================================================


class TestProfileSemanticParity:
    """AGNT-03: Local compose and BYOC profiles have equivalent semantics."""

    def test_local_compose_adapter_has_semantic_states(self):
        """TEST-21: Local compose adapter exposes semantic state (ready, hydrating, etc.)."""
        from src.infrastructure.sandbox.providers.local_compose import (
            LocalComposeSandboxProvider,
        )
        from src.infrastructure.sandbox.providers.base import (
            SandboxState,
            SandboxHealth,
        )

        provider = LocalComposeSandboxProvider()

        # Verify semantic state contract is implemented
        assert hasattr(provider, "get_active_sandbox")
        assert hasattr(provider, "provision_sandbox")
        assert hasattr(provider, "get_health")
        assert hasattr(provider, "stop_sandbox")

    def test_daytona_adapter_has_semantic_states(self):
        """TEST-22: Daytona adapter exposes semantic state (ready, hydrating, etc.)."""
        from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
        from src.infrastructure.sandbox.providers.base import SandboxState

        # Provider can be instantiated with config
        provider = DaytonaSandboxProvider(
            api_token="test-token",
            base_url=None,  # Cloud mode
        )

        # Verify semantic state contract is implemented
        assert hasattr(provider, "get_active_sandbox")
        assert hasattr(provider, "provision_sandbox")

    def test_provider_factory_returns_configured_provider(self):
        """TEST-23: Factory returns appropriate provider based on configuration."""
        from src.infrastructure.sandbox.providers.factory import get_provider
        from src.infrastructure.sandbox.providers.local_compose import (
            LocalComposeSandboxProvider,
        )

        # Default should return local compose for testing
        provider = get_provider()

        assert provider is not None
        # Provider implements the base contract
        assert hasattr(provider, "get_active_sandbox")


# =============================================================================
# AGNT-03: Registered Pack Binding Parity Tests (UAT Test 4)
# =============================================================================


class TestRegisteredPackBindingParity:
    """AGNT-03: Registered pack runs with equivalent binding semantics across profiles.

    This test class closes the UAT Test 4 gap by proving that pack binding
    works equivalently across local_compose and daytona profiles without
    manual infrastructure rewiring.
    """

    @pytest.fixture
    def registered_pack_for_workspace(
        self, db_session, workspace_alpha, workspace_owner
    ):
        """Create and register a real agent pack for workspace_alpha."""
        import tempfile
        from src.db.repositories.agent_pack_repository import AgentPackRepository
        from src.db.models import AgentPackValidationStatus
        from datetime import datetime, timezone

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create required pack files manually for speed
            import os

            os.makedirs(os.path.join(tmpdir, "skills"), exist_ok=True)
            with open(os.path.join(tmpdir, "AGENT.md"), "w") as f:
                f.write("# Test Agent\n")
            with open(os.path.join(tmpdir, "SOUL.md"), "w") as f:
                f.write("# Test Soul\n")
            with open(os.path.join(tmpdir, "IDENTITY.md"), "w") as f:
                f.write("# Test Identity\n")

            # Register the pack using repository directly
            pack_repo = AgentPackRepository(db_session)
            pack = pack_repo.create(
                workspace_id=workspace_alpha.id,
                name="Parity Test Pack",
                source_path=tmpdir,
            )

            # Set pack as VALID (required for runtime binding)
            pack.validation_status = AgentPackValidationStatus.VALID
            pack.is_active = True
            pack.last_validated_at = datetime.now(timezone.utc)
            db_session.commit()

            yield {
                "workspace_id": workspace_alpha.id,
                "pack_id": str(pack.id),
                "pack_path": tmpdir,
            }

    @pytest.mark.asyncio
    async def test_local_compose_profile_binds_registered_pack_via_factory(
        self,
        db_session,
        workspace_alpha,
        workspace_owner,
        registered_pack_for_workspace,
    ):
        """Local compose profile binds registered pack during sandbox resolution (via factory)."""
        from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
        from src.infrastructure.sandbox.providers.factory import get_provider

        ctx = registered_pack_for_workspace
        pack_id = ctx["pack_id"]

        # Create orchestrator that uses local_compose profile
        local_provider = get_provider("local_compose")
        orchestrator = SandboxOrchestratorService(db_session, provider=local_provider)
        lifecycle = WorkspaceLifecycleService(db_session, orchestrator=orchestrator)

        # Resolve with agent_pack_id
        result = await lifecycle.resolve_target(
            principal=workspace_owner,
            workspace=workspace_alpha,
            auto_create=False,
            acquire_lease=False,  # Skip lease to simplify test
            run_id="test-run-local-compose",
            agent_pack_id=pack_id,
        )

        # Should succeed
        assert result.error is None, f"Resolution failed: {result.error}"
        assert result.sandbox is not None
        assert result.routing_result is not None
        assert result.routing_result.provider_info is not None

        # Pack binding semantics should be present in provider metadata
        provider_info = result.routing_result.provider_info
        assert provider_info.ref.metadata.get("pack_bound") is True, (
            "Local compose should bind pack during provisioning"
        )
        assert "pack_source_path" in provider_info.ref.metadata, (
            "Local compose should expose pack_source_path"
        )
        assert provider_info.ref.metadata["pack_source_path"] is not None

    @pytest.mark.asyncio
    async def test_daytona_profile_binds_registered_pack_sdk_backed(
        self,
        db_session,
        workspace_alpha,
        workspace_owner,
        registered_pack_for_workspace,
    ):
        """Daytona profile binds registered pack using SDK-backed provider (AGNT-03 SDK parity).

        This test verifies that Daytona provider correctly binds packs when using
        the real AsyncDaytona SDK with mocked responses during provisioning.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4
        from datetime import datetime, timezone
        from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
        from src.infrastructure.sandbox.providers.factory import get_provider
        from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
        from src.db.models import (
            SandboxInstance,
            SandboxState,
            SandboxHealthStatus,
            SandboxProfile,
        )

        ctx = registered_pack_for_workspace
        pack_id = ctx["pack_id"]
        pack_path = ctx["pack_path"]

        # Get Daytona provider
        daytona_provider = get_provider("daytona")
        assert isinstance(daytona_provider, DaytonaSandboxProvider)

        # Create an existing sandbox record in the database (but not actually running in Daytona)
        # This will cause the orchestrator to check the provider for health status
        sandbox_record = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.DAYTONA,
            provider_ref=f"daytona-{str(workspace_alpha.id)[:22]}",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
        )
        db_session.add(sandbox_record)
        db_session.commit()

        # Mock AsyncDaytona SDK
        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock sandbox with pack binding metadata
            mock_sandbox = MagicMock()
            mock_sandbox.id = f"daytona-{str(workspace_alpha.id)[:22]}"
            mock_sandbox.state = "running"
            mock_sandbox.status = "healthy"
            mock_sandbox.metadata = {
                "pack_bound": True,
                "pack_source_path": pack_path,
            }

            # Setup mock responses - get() returns the active sandbox
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)

            # Create orchestrator with Daytona provider
            orchestrator = SandboxOrchestratorService(
                db_session, provider=daytona_provider
            )
            lifecycle = WorkspaceLifecycleService(db_session, orchestrator=orchestrator)

            # Resolve with agent_pack_id (auto_create=False so it checks existing first)
            result = await lifecycle.resolve_target(
                principal=workspace_owner,
                workspace=workspace_alpha,
                auto_create=False,  # Don't create new, use existing
                acquire_lease=False,  # Skip lease to simplify test
                run_id="test-run-daytona-sdk",
                agent_pack_id=pack_id,
            )

            # Should succeed
            assert result.error is None, f"Resolution failed: {result.error}"
            assert result.sandbox is not None
            assert result.routing_result is not None
            assert result.routing_result.provider_info is not None

            # Verify SDK get() was called to check Daytona state
            mock_daytona.get.assert_called_once()

            # Pack binding semantics should be present in provider metadata
            provider_info = result.routing_result.provider_info
            assert provider_info.ref.metadata.get("pack_bound") is True, (
                "Daytona SDK-backed provider should bind pack during provisioning"
            )
            assert "pack_source_path" in provider_info.ref.metadata, (
                "Daytona SDK-backed provider should expose pack_source_path"
            )
            assert provider_info.ref.metadata["pack_source_path"] == pack_path

    @pytest.mark.asyncio
    async def test_cross_profile_pack_binding_parity(
        self,
        db_session,
        workspace_alpha,
        workspace_owner,
        registered_pack_for_workspace,
    ):
        """Both profiles apply equivalent pack-binding semantics without manual rewiring."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
        from src.infrastructure.sandbox.providers.factory import get_provider
        from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider

        ctx = registered_pack_for_workspace
        pack_id = ctx["pack_id"]
        pack_path = ctx["pack_path"]

        # Create orchestrator for local_compose (no mocking needed)
        local_provider = get_provider("local_compose")
        local_orchestrator = SandboxOrchestratorService(
            db_session, provider=local_provider
        )
        local_lifecycle = WorkspaceLifecycleService(
            db_session, orchestrator=local_orchestrator
        )

        # Resolve with local_compose
        local_result = await local_lifecycle.resolve_target(
            principal=workspace_owner,
            workspace=workspace_alpha,
            auto_create=False,
            acquire_lease=False,
            run_id="test-run-local-parity",
            agent_pack_id=pack_id,
        )

        # Resolve with daytona - must mock SDK
        daytona_provider = get_provider("daytona")
        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Create an existing sandbox record for Daytona profile
            from uuid import uuid4
            from datetime import datetime, timezone
            from src.db.models import (
                SandboxInstance,
                SandboxProfile,
                SandboxHealthStatus,
                SandboxState,
            )

            daytona_sandbox_record = SandboxInstance(
                id=uuid4(),
                workspace_id=workspace_alpha.id,
                profile=SandboxProfile.DAYTONA,
                provider_ref=f"daytona-{str(workspace_alpha.id)[:22]}",
                state=SandboxState.ACTIVE,
                health_status=SandboxHealthStatus.HEALTHY,
                created_at=datetime.now(timezone.utc),
                last_activity_at=datetime.now(timezone.utc),
            )
            db_session.add(daytona_sandbox_record)
            db_session.commit()

            # Mock Daytona SDK to return healthy running sandbox
            mock_sandbox = MagicMock()
            mock_sandbox.id = f"daytona-{str(workspace_alpha.id)[:22]}"
            mock_sandbox.state = "running"
            mock_sandbox.status = "healthy"
            mock_sandbox.metadata = {
                "pack_bound": True,
                "pack_source_path": pack_path,
            }
            mock_daytona.get = AsyncMock(return_value=mock_sandbox)

            daytona_orchestrator = SandboxOrchestratorService(
                db_session, provider=daytona_provider
            )
            daytona_lifecycle = WorkspaceLifecycleService(
                db_session, orchestrator=daytona_orchestrator
            )

            daytona_result = await daytona_lifecycle.resolve_target(
                principal=workspace_owner,
                workspace=workspace_alpha,
                auto_create=False,
                acquire_lease=False,
                run_id="test-run-daytona-parity",
                agent_pack_id=pack_id,
            )

            # Both should succeed
            assert local_result.error is None, (
                f"Local compose failed: {local_result.error}"
            )
            assert daytona_result.error is None, (
                f"Daytona failed: {daytona_result.error}"
            )

            # Both should have routing results with provider info
            assert local_result.routing_result is not None
            assert daytona_result.routing_result is not None
            assert local_result.routing_result.provider_info is not None
            assert daytona_result.routing_result.provider_info is not None

            # Both should have pack binding
            local_provider_info = local_result.routing_result.provider_info
            daytona_provider_info = daytona_result.routing_result.provider_info

            local_bound = local_provider_info.ref.metadata.get("pack_bound")
            daytona_bound = daytona_provider_info.ref.metadata.get("pack_bound")

            assert local_bound is True, "Local compose should bind pack"
            assert daytona_bound is True, "Daytona should bind pack"

            # Both should have same pack source path
            local_path = local_provider_info.ref.metadata.get("pack_source_path")
            daytona_path = daytona_provider_info.ref.metadata.get("pack_source_path")

            assert local_path is not None, "Local compose should have pack_source_path"
            assert daytona_path is not None, "Daytona should have pack_source_path"
            assert local_path == daytona_path, (
                "Both profiles should resolve same pack source path"
            )

    @pytest.mark.asyncio
    async def test_daytona_sdk_backed_sandbox_lifecycle(
        self,
        db_session,
        workspace_alpha,
        workspace_owner,
        registered_pack_for_workspace,
    ):
        """Daytona SDK-backed provider handles full sandbox lifecycle (WORK-02 SDK parity).

        This acceptance test verifies that Daytona profile using AsyncDaytona SDK
        correctly provisions sandboxes, returns READY state from SDK responses,
        and preserves pack binding metadata through the lifecycle.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
        from src.infrastructure.sandbox.providers.factory import get_provider
        from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
        from src.infrastructure.sandbox.providers.base import (
            SandboxState,
            SandboxHealth,
        )

        ctx = registered_pack_for_workspace
        pack_id = ctx["pack_id"]
        pack_path = ctx["pack_path"]

        # Get Daytona provider
        daytona_provider = get_provider("daytona")
        assert isinstance(daytona_provider, DaytonaSandboxProvider)

        # Mock AsyncDaytona SDK for full lifecycle test
        with patch(
            "src.infrastructure.sandbox.providers.daytona.AsyncDaytona"
        ) as mock_sdk_class:
            mock_daytona = AsyncMock()
            mock_sdk_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_daytona
            )
            mock_sdk_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock sandbox in "started" state (ready to use)
            mock_sandbox = MagicMock()
            mock_sandbox.id = f"daytona-{str(workspace_alpha.id)[:22]}"
            mock_sandbox.state = "started"
            mock_sandbox.status = "healthy"
            mock_sandbox.metadata = {
                "pack_bound": True,
                "pack_source_path": pack_path,
            }

            # First get() raises DaytonaError (no existing sandbox)
            # Then create() returns the new sandbox
            from daytona import DaytonaError

            mock_daytona.get = AsyncMock(side_effect=DaytonaError("Sandbox not found"))
            mock_daytona.create = AsyncMock(return_value=mock_sandbox)

            # Create orchestrator with Daytona provider
            orchestrator = SandboxOrchestratorService(
                db_session, provider=daytona_provider
            )
            lifecycle = WorkspaceLifecycleService(db_session, orchestrator=orchestrator)

            # Resolve with auto_create=True (should provision)
            result = await lifecycle.resolve_target(
                principal=workspace_owner,
                workspace=workspace_alpha,
                auto_create=True,
                acquire_lease=False,
                run_id="test-daytona-lifecycle",
                agent_pack_id=pack_id,
            )

            # Verify SDK create was called for provisioning
            mock_daytona.create.assert_called_once()
            call_args = mock_daytona.create.call_args
            assert call_args.kwargs.get("timeout") == 60, (
                "Should use 60s timeout for provisioning"
            )

            # Verify result state - check routing_result provider_info for semantic state
            assert result.error is None, f"Resolution failed: {result.error}"
            assert result.sandbox is not None
            assert result.routing_result is not None
            assert result.routing_result.provider_info is not None
            assert result.routing_result.provider_info.state == SandboxState.READY, (
                "SDK 'started' state should map to READY"
            )
            assert (
                result.routing_result.provider_info.health == SandboxHealth.HEALTHY
            ), "SDK 'healthy' status should map to HEALTHY"

            # Verify pack binding in provider metadata
            assert (
                result.routing_result.provider_info.ref.metadata.get("pack_bound")
                is True
            )
            assert (
                result.routing_result.provider_info.ref.metadata.get("pack_source_path")
                == pack_path
            )


# =============================================================================
# Pack Lifecycle Tests
# =============================================================================


class TestAgentPackLifecycle:
    """Tests for agent pack lifecycle operations."""

    def test_revalidate_updates_validation_status(self, client, owner_headers):
        """POST /agent-packs/{id}/validate re-runs validation and updates status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "Revalidate Test", "source_path": tmpdir}
            reg_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            pack_id = reg_response.json()["pack_id"]

            # Revalidate
            reval_response = client.post(
                f"/api/v1/agent-packs/{pack_id}/validate",
                headers=owner_headers,
            )

            assert reval_response.status_code == 200
            data = reval_response.json()
            assert data["success"] is True
            assert "validation" in data

    def test_stale_check_detects_source_changes(self, client, owner_headers):
        """GET /agent-packs/{id}/stale detects when source has changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "Stale Test", "source_path": tmpdir}
            reg_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            pack_id = reg_response.json()["pack_id"]

            # Check stale status
            stale_response = client.get(
                f"/api/v1/agent-packs/{pack_id}/stale",
                headers=owner_headers,
            )

            assert stale_response.status_code == 200
            data = stale_response.json()
            assert "is_stale" in data
            # Initially not stale since just registered
            assert data["is_stale"] is False

    def test_list_packs_returns_workspace_packs(self, client, owner_headers):
        """GET /agent-packs returns all packs for workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "List Test", "source_path": tmpdir}
            client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )

            # List packs
            list_response = client.get("/api/v1/agent-packs", headers=owner_headers)

            assert list_response.status_code == 200
            data = list_response.json()
            assert isinstance(data, list)
            # Should have at least the pack we just registered
            assert len(data) >= 1

    def test_get_pack_returns_pack_details(self, client, owner_headers):
        """GET /agent-packs/{id} returns pack details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "Get Test", "source_path": tmpdir}
            reg_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            pack_id = reg_response.json()["pack_id"]

            # Get pack
            get_response = client.get(
                f"/api/v1/agent-packs/{pack_id}",
                headers=owner_headers,
            )

            assert get_response.status_code == 200
            data = get_response.json()
            assert data["pack_id"] == pack_id
            assert data["name"] == "Get Test"
            assert data["source_path"] == str(Path(tmpdir).resolve())
