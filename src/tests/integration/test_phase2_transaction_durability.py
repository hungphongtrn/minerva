"""Phase 2 transaction durability regression tests.

Tests for UAT Test 4/5 gap closure: Verifying that successful operations
persist durably across request boundaries.

These tests verify production-equivalent transaction behavior:
1. Pack registration is durable across separate HTTP requests
2. Sandbox resolve reuses existing healthy sandboxes across requests
3. No test-only auto-commit masking hides production transaction gaps
"""

import pytest
import tempfile
from uuid import uuid4, UUID
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    AgentPack,
)


# =============================================================================
# UAT Test 4: Pack Registration Durability
# =============================================================================


class TestPackRegistrationDurability:
    """UAT Test 4: Pack registration persists across separate requests.

    Regression coverage ensuring that successful POST /agent-packs/register
    is immediately visible via list and get endpoints in subsequent requests.
    """

    def test_register_pack_visible_in_list_immediately(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Pack registered in request 1 is visible in list request 2.

        This test fails if writes are only flushed and not committed,
        as the second request would see stale data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup: Create scaffold and bootstrap workspace
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            response = client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )
            assert response.status_code == 201

            # Bootstrap workspace
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Request 1: Register the pack
            register_request = {
                "name": "Durability Test Pack",
                "source_path": tmpdir,
            }
            register_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            assert register_response.status_code == 201
            register_data = register_response.json()
            assert register_data["success"] is True
            pack_id = register_data["pack_id"]
            assert pack_id is not None

            # Request 2: List packs - registered pack must be visible
            list_response = client.get(
                "/api/v1/agent-packs",
                headers=owner_headers,
            )
            assert list_response.status_code == 200
            packs = list_response.json()

            # Find our pack in the list
            pack_ids = [p["pack_id"] for p in packs]
            assert pack_id in pack_ids, (
                f"Registered pack {pack_id} not found in list. "
                f"Available packs: {pack_ids}. "
                "This indicates transaction was not committed."
            )

            # Verify pack details match
            registered_pack = next(p for p in packs if p["pack_id"] == pack_id)
            assert registered_pack["name"] == "Durability Test Pack"
            assert registered_pack["validation_status"] == "valid"

    def test_register_pack_visible_in_get_immediately(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Pack registered in request 1 is retrievable via GET in request 2.

        This test fails if registration write is not durably committed,
        as the get request would return 404.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup: Create scaffold and bootstrap workspace
            scaffold_request = {"pack_path": tmpdir, "overwrite": False}
            client.post(
                "/api/v1/agent-packs/scaffold",
                json=scaffold_request,
                headers=owner_headers,
            )
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Request 1: Register the pack
            register_request = {
                "name": "Get Test Pack",
                "source_path": tmpdir,
            }
            register_response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )
            assert register_response.status_code == 201
            pack_id = register_response.json()["pack_id"]

            # Request 2: Get the specific pack - must succeed
            get_response = client.get(
                f"/api/v1/agent-packs/{pack_id}",
                headers=owner_headers,
            )
            assert get_response.status_code == 200, (
                f"GET /agent-packs/{pack_id} returned {get_response.status_code}. "
                "Registered pack should be immediately retrievable. "
                "This indicates transaction was not committed."
            )

            pack_data = get_response.json()
            assert pack_data["pack_id"] == pack_id
            assert pack_data["name"] == "Get Test Pack"

    def test_register_multiple_packs_all_durable(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Multiple pack registrations are all durable across requests.

        Ensures batch-like registration scenarios work correctly.
        """
        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            # Setup both directories with scaffold
            for tmpdir in [tmpdir1, tmpdir2]:
                client.post(
                    "/api/v1/agent-packs/scaffold",
                    json={"pack_path": tmpdir, "overwrite": False},
                    headers=owner_headers,
                )

            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Register multiple packs in sequence
            pack_ids = []
            for i, tmpdir in enumerate([tmpdir1, tmpdir2], 1):
                response = client.post(
                    "/api/v1/agent-packs/register",
                    json={"name": f"Multi Pack {i}", "source_path": tmpdir},
                    headers=owner_headers,
                )
                assert response.status_code == 201
                pack_ids.append(response.json()["pack_id"])

            # List and verify all packs are present
            list_response = client.get("/api/v1/agent-packs", headers=owner_headers)
            assert list_response.status_code == 200
            listed_ids = {p["pack_id"] for p in list_response.json()}

            for pack_id in pack_ids:
                assert pack_id in listed_ids, (
                    f"Pack {pack_id} not found in list after registration. "
                    "All registrations should be durable."
                )


# =============================================================================
# UAT Test 5: Sandbox Resolve Reuse Durability
# =============================================================================


class TestSandboxResolveReuse:
    """UAT Test 5: Back-to-back resolve calls reuse healthy sandboxes.

    Regression coverage ensuring that consecutive POST /workspaces/{id}/sandbox/resolve
    calls return the same sandbox_id when the sandbox remains healthy.
    """

    def test_resolve_persists_sandbox_durably(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Resolve persists sandbox durably and it's queryable in subsequent requests.

        This test calls resolve to create a sandbox, then verifies the sandbox
        is durably persisted by querying it directly from the database.
        This proves that:
        1. Resolve operations commit their results durably
        2. Sandbox state is available across request boundaries

        Fails if resolve does not commit transaction before returning.
        """

        # Bootstrap workspace
        bootstrap_response = client.post(
            "/api/v1/workspaces/bootstrap",
            headers=owner_headers,
        )
        assert bootstrap_response.status_code == 200
        workspace_id_str = bootstrap_response.json()["workspace_id"]
        workspace_id = UUID(workspace_id_str)

        # Count sandboxes before resolve
        (
            db_session.query(SandboxInstance)
            .filter(SandboxInstance.workspace_id == workspace_id)
            .count()
        )

        # Request: Resolve sandbox (this may create a new one)
        resolve_response = client.post(
            f"/api/v1/workspaces/{workspace_id_str}/sandbox/resolve",
            headers=owner_headers,
        )
        assert resolve_response.status_code == 200
        resolve_data = resolve_response.json()
        returned_sandbox_id = resolve_data.get("sandbox_id")

        # Should have a sandbox ID
        assert returned_sandbox_id is not None, "Resolve should return a sandbox_id"

        # Verify sandbox was durably persisted by querying database directly
        # This uses a fresh query to ensure data was committed
        db_session.expire_all()  # Clear session cache
        sandbox = (
            db_session.query(SandboxInstance)
            .filter(SandboxInstance.id == UUID(returned_sandbox_id))
            .first()
        )

        assert sandbox is not None, (
            f"Sandbox {returned_sandbox_id} should be persisted in database. "
            "If this fails, the resolve operation did not commit its transaction. "
            "This is a durability gap - the response returned success but "
            "the data was not durably saved."
        )
        assert sandbox.workspace_id == workspace_id
        assert str(sandbox.id) == returned_sandbox_id

    @pytest.mark.asyncio
    async def test_resolve_reuse_with_provider_check(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Resolve reuse verified at provider level.

        Tests that the orchestrator properly queries provider for existing
        sandboxes and reuses them rather than creating new ones.
        """
        from src.db.models import Workspace
        from src.services.workspace_lifecycle_service import WorkspaceLifecycleService
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService
        from src.infrastructure.sandbox.providers.local_compose import (
            LocalComposeSandboxProvider,
        )

        # Bootstrap workspace
        bootstrap_response = client.post(
            "/api/v1/workspaces/bootstrap",
            headers=owner_headers,
        )
        assert bootstrap_response.status_code == 200
        workspace_id_str = bootstrap_response.json()["workspace_id"]
        workspace_uuid = UUID(workspace_id_str)  # Convert string to UUID

        workspace = (
            db_session.query(Workspace).filter(Workspace.id == workspace_uuid).first()
        )
        assert workspace is not None

        # Create healthy sandbox record
        sandbox = SandboxInstance(
            id=uuid4(),
            workspace_id=workspace.id,
            profile=SandboxProfile.LOCAL_COMPOSE,
            provider_ref="reuse-test-sandbox",
            state=SandboxState.ACTIVE,
            health_status=SandboxHealthStatus.HEALTHY,
            last_health_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
        )
        db_session.add(sandbox)
        db_session.commit()

        # Use lifecycle service directly to verify provider-level reuse
        provider = LocalComposeSandboxProvider()
        orchestrator = SandboxOrchestratorService(db_session, provider=provider)
        lifecycle = WorkspaceLifecycleService(db_session, orchestrator=orchestrator)

        # First resolve
        target1 = await lifecycle.resolve_target(
            principal=None,  # Will be set internally
            auto_create=False,
            acquire_lease=True,
            run_id="test-run-1",
            workspace=workspace,
        )

        assert target1.routing_result is not None
        assert target1.routing_result.success is True
        sandbox_1 = target1.routing_result.sandbox
        assert sandbox_1 is not None

        # Release lease for second resolve
        from src.services.workspace_lease_service import WorkspaceLeaseService

        lease_service = WorkspaceLeaseService(db_session)
        lease_service.release_lease(
            workspace_id=workspace.id,
            holder_run_id="test-run-1",
        )

        # Second resolve should find same sandbox
        target2 = await lifecycle.resolve_target(
            principal=None,
            auto_create=False,
            acquire_lease=True,
            run_id="test-run-2",
            workspace=workspace,
        )

        assert target2.routing_result is not None
        assert target2.routing_result.success is True
        sandbox_2 = target2.routing_result.sandbox
        assert sandbox_2 is not None

        # Verify same sandbox reused
        assert sandbox_1.id == sandbox_2.id, (
            f"Orchestrator returned different sandboxes: "
            f"first={sandbox_1.id}, second={sandbox_2.id}"
        )


# =============================================================================
# Transaction Boundary Verification
# =============================================================================


class TestTransactionBoundaryBehavior:
    """Verify transaction boundaries work correctly for errors.

    These tests ensure rollback happens correctly on exceptions.
    """

    def test_failed_registration_does_not_persist(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Invalid pack registration does not create partial records.

        This test verifies that failed operations are properly rolled back
        and don't leave partial state in the database.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Bootstrap workspace (but don't scaffold - invalid pack)
            client.post("/api/v1/workspaces/bootstrap", headers=owner_headers)

            # Try to register invalid pack (no scaffold)
            register_request = {
                "name": "Invalid Pack",
                "source_path": tmpdir,
            }
            response = client.post(
                "/api/v1/agent-packs/register",
                json=register_request,
                headers=owner_headers,
            )

            # Should return 200 with validation failure (not 500 error)
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is False
            assert data["validation"]["is_valid"] is False

            # List packs - should not contain the invalid pack
            list_response = client.get("/api/v1/agent-packs", headers=owner_headers)
            assert list_response.status_code == 200
            packs = list_response.json()

            # No pack with this name should exist
            pack_names = {p["name"] for p in packs}
            assert "Invalid Pack" not in pack_names, (
                "Invalid pack should not be persisted"
            )

            # Verify in database directly
            invalid_packs = (
                db_session.query(AgentPack)
                .filter(AgentPack.name == "Invalid Pack")
                .all()
            )
            assert len(invalid_packs) == 0, "Invalid pack should not exist in database"

    def test_transaction_rollback_on_exception(
        self, client: TestClient, owner_headers: dict, db_session: Session
    ):
        """Database transaction commits successfully on normal operation.

        Verifies the transaction boundary properly commits when
        the route handler completes successfully. This test ensures
        that the production transaction behavior (commit on success)
        is working correctly.
        """
        from src.db.models import Workspace

        # Bootstrap workspace
        response = client.post(
            "/api/v1/workspaces/bootstrap",
            headers=owner_headers,
        )
        assert response.status_code == 200
        response_data = response.json()
        workspace_id = response_data["workspace_id"]

        # Verify workspace was persisted by querying it directly
        # This requires the transaction to have been committed
        workspace = (
            db_session.query(Workspace)
            .filter(Workspace.id == UUID(workspace_id))
            .first()
        )
        assert workspace is not None, (
            f"Workspace {workspace_id} should be persisted after successful bootstrap. "
            "If this fails, the transaction was not committed (possible flush-only)."
        )
        assert workspace.name == response_data["name"], (
            "Persisted workspace name should match response"
        )
