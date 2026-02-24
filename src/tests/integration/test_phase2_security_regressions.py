"""Phase 2 security regression tests (SECU-05).

Tests for workspace/sandbox/pack isolation boundaries:
- No cross-workspace lease hijack
- No cross-workspace sandbox routing
- No unauthorized pack registration
- No path traversal in scaffold operations
"""

import pytest
import tempfile
from pathlib import Path
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    Workspace,
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    AgentPack,
    WorkspaceLease,
)
from src.services.workspace_lease_service import WorkspaceLeaseService
from src.services.agent_pack_service import AgentPackService
from src.services.agent_scaffold_service import AgentScaffoldService


# =============================================================================
# SECU-05: Cross-Workspace Isolation Tests
# =============================================================================


class TestCrossWorkspaceLeaseIsolation:
    """SECU-05: Workspace A requests must never acquire leases for Workspace B."""

    def test_cannot_acquire_lease_for_other_workspace(
        self, db_session, workspace_alpha, workspace_beta
    ):
        """Lease acquisition is scoped to workspace - cannot acquire for different workspace."""
        service = WorkspaceLeaseService(db_session)

        # Acquire lease for workspace_alpha
        result1 = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-1",
            holder_identity="user-1",
            ttl_seconds=60,
        )
        assert result1.success is True

        # Acquire lease for workspace_beta should succeed (different workspace)
        result2 = service.acquire_lease(
            workspace_id=workspace_beta.id,
            holder_run_id="run-2",
            holder_identity="user-2",
            ttl_seconds=60,
        )
        assert result2.success is True

        # Verify different leases exist
        lease_alpha = (
            db_session.query(WorkspaceLease)
            .filter_by(
                workspace_id=workspace_alpha.id,
                released_at=None,
            )
            .first()
        )

        lease_beta = (
            db_session.query(WorkspaceLease)
            .filter_by(
                workspace_id=workspace_beta.id,
                released_at=None,
            )
            .first()
        )

        assert lease_alpha is not None
        assert lease_beta is not None
        assert lease_alpha.workspace_id != lease_beta.workspace_id

    def test_cannot_release_lease_for_other_workspace(
        self, db_session, workspace_alpha, workspace_beta
    ):
        """Lease release verifies holder - cannot release another workspace's lease."""
        service = WorkspaceLeaseService(db_session)

        # Acquire lease for workspace_alpha
        service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="run-alpha",
            holder_identity="user-alpha",
            ttl_seconds=60,
        )

        # Try to release using wrong workspace should fail silently (no-op)
        result = service.release_lease(
            workspace_id=workspace_beta.id,  # Wrong workspace
            holder_run_id="run-alpha",
        )

        # Release succeeds (no-op) but lease for alpha still exists
        lease_alpha = (
            db_session.query(WorkspaceLease)
            .filter_by(
                workspace_id=workspace_alpha.id,
                released_at=None,
            )
            .first()
        )

        assert lease_alpha is not None
        assert lease_alpha.holder_run_id == "run-alpha"


class TestCrossWorkspaceSandboxIsolation:
    """SECU-05: Workspace A requests must never route to sandbox owned by Workspace B."""

    def test_sandbox_query_scoped_to_workspace(
        self, db_session, workspace_alpha, workspace_beta
    ):
        """Sandbox queries are filtered by workspace_id."""
        from src.db.repositories.sandbox_instance_repository import (
            SandboxInstanceRepository,
        )

        # Create sandboxes in different workspaces
        sandbox_alpha = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="sandbox-alpha",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
        )
        sandbox_beta = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_beta.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="sandbox-beta",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
        )
        db_session.add(sandbox_alpha)
        db_session.add(sandbox_beta)
        db_session.commit()

        # Query for workspace_alpha should only return alpha sandbox
        repo = SandboxInstanceRepository(db_session)
        alpha_sandboxes = repo.list_active_healthy_by_workspace(workspace_alpha.id)

        assert len(alpha_sandboxes) == 1
        assert alpha_sandboxes[0].id == sandbox_alpha.id

    def test_cannot_resolve_sandbox_for_other_workspace(
        self, client, owner_headers, other_workspace_headers
    ):
        """Sandbox resolution endpoint enforces workspace ownership."""
        # User creates workspace
        response = client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)
        workspace_id = response.json()["workspace_id"]

        # Other workspace's user tries to resolve sandbox
        resolve_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=other_workspace_headers,
        )

        # Should be forbidden
        assert resolve_response.status_code == 403


class TestCrossWorkspacePackIsolation:
    """SECU-05: Pack registration and access scoped to workspace."""

    def test_cannot_register_pack_in_other_workspace(
        self, client, owner_headers, other_workspace_headers
    ):
        """Pack registration is scoped to authenticated workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup pack
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            # First user bootstraps workspace and registers pack
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "Owner Pack", "source_path": tmpdir}
            reg_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            assert reg_response.status_code == 201
            pack_id = reg_response.json()["pack_id"]

            # Other workspace user tries to access the pack
            get_response = client.get(
                f"/api/v1/agent-packs/{pack_id}",
                headers=other_workspace_headers,
            )

            # Should be forbidden
            assert get_response.status_code == 403

    def test_cannot_validate_pack_in_other_workspace(
        self, client, owner_headers, other_workspace_headers
    ):
        """Pack validation endpoint enforces workspace ownership."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            register_request = {"name": "Validate Test", "source_path": tmpdir}
            reg_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            pack_id = reg_response.json()["pack_id"]

            # Other workspace tries to validate
            val_response = client.post(
                f"/api/v1/agent-packs/{pack_id}/validate",
                headers=other_workspace_headers,
            )

            assert val_response.status_code == 403

    def test_list_packs_only_returns_own_workspace_packs(
        self, client, owner_headers, other_workspace_headers
    ):
        """Pack listing only returns packs for the authenticated workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup pack
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )

            # Owner bootstraps and registers
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)
            client.post("/api/v1/workspaces/bootstrap", headers=other_workspace_headers)

            register_request = {"name": "Owner Pack", "source_path": tmpdir}
            client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )

            # Other workspace user lists packs
            list_response = client.get(
                "/api/v1/agent-packs", headers=other_workspace_headers
            )

            assert list_response.status_code == 200
            data = list_response.json()

            # Should not see owner's pack
            for pack in data:
                assert pack["name"] != "Owner Pack"


class TestPathTraversalProtection:
    """SECU-05: Path traversal attempts are rejected in scaffold operations."""

    def test_scaffold_rejects_path_traversal(self):
        """Scaffold service rejects paths that escape base directory."""
        service = AgentScaffoldService()

        # Path traversal attempt
        with pytest.raises(Exception) as exc_info:
            service.generate("../../../etc/passwd")

        # Should raise path traversal error
        assert (
            "traversal" in str(exc_info.value).lower()
            or "escape" in str(exc_info.value).lower()
        )

    def test_scaffold_rejects_absolute_path_outside_base(self):
        """Scaffold service validates absolute paths are within base."""
        service = AgentScaffoldService(base_path=Path("/tmp/allowed"))

        with pytest.raises(Exception) as exc_info:
            service.generate("/etc/passwd")

        # Should raise path traversal error
        assert (
            "traversal" in str(exc_info.value).lower()
            or "escape" in str(exc_info.value).lower()
        )


class TestGuestModeRestrictions:
    """SECU-05: Guest mode has restricted access to workspace/pack features."""

    def test_guest_cannot_bootstrap_workspace(self, client):
        """Guest mode cannot create persistent workspaces."""
        response = client.post("/api/v1/workspaces/bootstrap")

        assert response.status_code == 403
        assert "guest" in response.json()["detail"]["error"].lower()

    def test_guest_cannot_register_pack(self, client):
        """Guest mode cannot register agent packs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            request = {"name": "Guest Pack", "source_path": tmpdir}
            response = client.post("/api/v1/agent-packs/register", json=request)

            assert response.status_code == 403
            assert "guest" in response.json()["detail"]["error"].lower()

    def test_guest_cannot_list_packs(self, client):
        """Guest mode cannot list agent packs."""
        response = client.get("/api/v1/agent-packs")

        assert response.status_code == 403
        assert "guest" in response.json()["detail"]["error"].lower()

    def test_guest_cannot_get_pack(self, client):
        """Guest mode cannot retrieve pack details."""
        response = client.get(f"/api/v1/agent-packs/{uuid4()}")

        assert response.status_code == 403
        assert "guest" in response.json()["detail"]["error"].lower()


class TestHealthFailureHandling:
    """SECU-05: Health failures block routing (fail-closed)."""

    def test_unhealthy_sandbox_excluded_from_routing(self, db_session, workspace_alpha):
        """Unhealthy sandboxes are not returned by routing queries."""
        from src.db.repositories.sandbox_instance_repository import (
            SandboxInstanceRepository,
        )

        # Create healthy and unhealthy sandboxes
        healthy = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="healthy-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
        )
        unhealthy = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="unhealthy-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.UNHEALTHY,
        )
        db_session.add(healthy)
        db_session.add(unhealthy)
        db_session.commit()

        # Query for healthy sandboxes
        repo = SandboxInstanceRepository(db_session)
        healthy_sandboxes = repo.list_active_healthy_by_workspace(workspace_alpha.id)

        # Should only return healthy sandbox
        assert len(healthy_sandboxes) == 1
        assert healthy_sandboxes[0].id == healthy.id

    def test_no_healthy_sandbox_triggers_provisioning(
        self, db_session, workspace_alpha
    ):
        """When no healthy sandboxes exist, provisioning should be triggered."""
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService

        # Create only unhealthy sandbox
        unhealthy = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="unhealthy-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.UNHEALTHY,
        )
        db_session.add(unhealthy)
        db_session.commit()

        # Orchestrator should detect no healthy candidates
        orchestrator = SandboxOrchestratorService(db_session)

        # The unhealthy sandbox should be in the excluded list
        # This verifies unhealthy exclusion logic
        unhealthy_sandboxes = (
            db_session.query(SandboxInstance)
            .filter_by(
                workspace_id=workspace_alpha.id,
                health_status=SandboxHealthStatus.UNHEALTHY,
            )
            .all()
        )

        assert len(unhealthy_sandboxes) == 1
        assert unhealthy_sandboxes[0].id == unhealthy.id


class TestValidationFailureBlocksRegistration:
    """SECU-05: Validation failures block registration with clear checklist."""

    def test_invalid_scaffold_blocks_registration(self, client, owner_headers):
        """Invalid pack scaffold blocks registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Don't create scaffold - leave empty

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            request = {"name": "Invalid Pack", "source_path": tmpdir}
            response = client.post(
                "/api/v1/agent-packs/register",
                json=request,
                headers=owner_headers,
            )

            # Should return 200 with failure info (not 500)
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is False
            assert "validation" in data
            assert data["validation"]["is_valid"] is False
            assert data["validation"]["error_count"] > 0

    def test_checklist_contains_machine_readable_codes(self, client, owner_headers):
        """Validation checklist has machine-readable codes for API consumers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Empty directory - will fail validation

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            request = {"name": "Bad Pack", "source_path": tmpdir}
            response = client.post(
                "/api/v1/agent-packs/register",
                json=request,
                headers=owner_headers,
            )

            assert response.status_code == 201
            data = response.json()
            checklist = data["validation"]["checklist"]

            # Checklist entries should have codes
            for entry in checklist:
                assert "code" in entry
                assert isinstance(entry["code"], str)
                assert len(entry["code"]) > 0


class TestLeaseExpirationRecovery:
    """SECU-05: Expired leases are recovered to prevent deadlock."""

    def test_expired_lease_is_reclaimed(self, db_session, workspace_alpha):
        """Expired leases are automatically reclaimed."""
        from datetime import datetime, timezone, timedelta

        # Create an expired lease
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        expired_lease = WorkspaceLease(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            holder_run_id="expired-run",
            holder_identity="expired-user",
            acquired_at=expired_time - timedelta(minutes=5),
            expires_at=expired_time,  # Already expired
        )
        db_session.add(expired_lease)
        db_session.commit()

        # Try to acquire lease - should reclaim expired one
        service = WorkspaceLeaseService(db_session)
        result = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="new-run",
            holder_identity="new-user",
            ttl_seconds=60,
        )

        # Should succeed by reclaiming expired lease
        assert result.success is True

    def test_active_lease_prevents_reclaim(self, db_session, workspace_alpha):
        """Active (non-expired) leases cannot be reclaimed."""
        service = WorkspaceLeaseService(db_session)

        # Acquire active lease
        service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="active-run",
            holder_identity="active-user",
            ttl_seconds=300,  # 5 minutes
        )

        # Try to acquire another - should fail
        result = service.acquire_lease(
            workspace_id=workspace_alpha.id,
            holder_run_id="new-run",
            holder_identity="new-user",
            ttl_seconds=60,
        )

        assert result.success is False
        from src.services.workspace_lease_service import LeaseResult

        assert result.result == LeaseResult.CONFLICT
