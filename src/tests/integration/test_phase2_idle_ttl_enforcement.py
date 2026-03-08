"""Integration tests for Phase 2 idle TTL enforcement.

Validates that TTL-expired sandboxes are automatically stopped during
routing, replacement sandboxes are provisioned, and state transitions
are durably persisted across requests.

Closes UAT Test 9.
"""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from src.db.models import (
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    Workspace,
)
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository
from src.infrastructure.sandbox.providers.local_compose import (
    LocalComposeSandboxProvider,
)
from src.infrastructure.sandbox.providers.base import (
    SandboxState as ProviderSandboxState,
    SandboxHealth as ProviderSandboxHealth,
)


def _register_sandbox_in_provider(
    provider: LocalComposeSandboxProvider,
    workspace_id: UUID,
    provider_ref: str,
    state: ProviderSandboxState = ProviderSandboxState.READY,
    health: ProviderSandboxHealth = ProviderSandboxHealth.HEALTHY,
    last_activity_minutes_ago: int = 0,
):
    """Register a sandbox in the provider's in-memory registry.

    This ensures the provider knows about sandboxes created directly in the database.
    """
    # Access the provider's internal registry
    now = datetime.now()
    provider._sandboxes[provider_ref] = {
        "workspace_id": workspace_id,
        "state": state,
        "health": health,
        "created_at": now,
        "last_activity_at": now - timedelta(minutes=last_activity_minutes_ago),
        "config": None,
        "provider_state": "running",
    }


@pytest.fixture
def expired_sandbox(
    db_session: Session,
    workspace_alpha: Workspace,
    provider_singleton: LocalComposeSandboxProvider,
) -> SandboxInstance:
    """Create a sandbox that has exceeded idle TTL."""
    repo = SandboxInstanceRepository(db_session)

    # Create sandbox with last activity well in the past
    sandbox = repo.create(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
        idle_ttl_seconds=300,  # 5 minute TTL
    )

    # Set state to ACTIVE with last activity 10 minutes ago (exceeds TTL)
    ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
    sandbox.last_activity_at = ten_minutes_ago
    sandbox.state = SandboxState.ACTIVE
    sandbox.health_status = SandboxHealthStatus.HEALTHY
    sandbox.provider_ref = "test-provider-ref-expired"

    db_session.commit()
    db_session.refresh(sandbox)

    # Also register in provider so health checks work
    _register_sandbox_in_provider(
        provider=provider_singleton,
        workspace_id=workspace_alpha.id,
        provider_ref=sandbox.provider_ref,
        last_activity_minutes_ago=10,
    )

    return sandbox


@pytest.fixture
def active_recent_sandbox(
    db_session: Session,
    workspace_alpha: Workspace,
    provider_singleton: LocalComposeSandboxProvider,
) -> SandboxInstance:
    """Create a sandbox with recent activity (within TTL)."""
    repo = SandboxInstanceRepository(db_session)

    # Create sandbox with recent activity
    sandbox = repo.create(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
        idle_ttl_seconds=300,  # 5 minute TTL
    )

    # Set state to ACTIVE with recent activity (within TTL)
    sandbox.last_activity_at = datetime.utcnow() - timedelta(minutes=1)
    sandbox.state = SandboxState.ACTIVE
    sandbox.health_status = SandboxHealthStatus.HEALTHY
    sandbox.provider_ref = "test-provider-ref-recent"

    db_session.commit()
    db_session.refresh(sandbox)

    # Also register in provider so health checks work
    _register_sandbox_in_provider(
        provider=provider_singleton,
        workspace_id=workspace_alpha.id,
        provider_ref=sandbox.provider_ref,
        last_activity_minutes_ago=1,
    )

    return sandbox


@pytest.fixture
def auth_headers_with_workspace(
    owner_headers: dict,
) -> dict:
    """Return owner auth headers - workspace ownership is verified by route."""
    return owner_headers


class TestTTLCleanupBeforeRouting:
    """Test that TTL cleanup is enforced before routing decisions."""

    def test_expired_sandbox_not_routed(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """TTL-expired sandbox should not be routed to; should be stopped and replaced."""
        workspace_id = str(workspace_alpha.id)
        expired_id = str(expired_sandbox.id)

        # Verify sandbox is initially active
        db_session.refresh(expired_sandbox)
        assert expired_sandbox.state == SandboxState.ACTIVE
        assert expired_sandbox.health_status == SandboxHealthStatus.HEALTHY

        # Call resolve endpoint
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )

        # Should succeed with new sandbox provisioned
        assert response.status_code == 200
        data = response.json()
        assert data["sandbox_id"] is not None
        assert data["sandbox_id"] != expired_id  # Different sandbox
        assert data["ttl_cleanup_applied"] is True
        assert data["ttl_stopped_count"] >= 1
        assert data["ttl_stopped_ids"] is not None
        assert expired_id in data["ttl_stopped_ids"]
        assert "TTL" in (data["ttl_cleanup_reason"] or "")

    def test_recent_sandbox_not_cleaned(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        active_recent_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """Sandbox with recent activity (within TTL) should NOT be cleaned up."""
        workspace_id = str(workspace_alpha.id)
        str(active_recent_sandbox.id)

        # Call resolve endpoint
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )

        # Should succeed
        assert response.status_code == 200
        data = response.json()
        # The sandbox should not be TTL-cleaned (not in stopped_sandbox_ids)
        # Note: Sandbox may be marked unhealthy if provider doesn't know about it,
        # but it should NOT be TTL-stopped
        assert data["ttl_cleanup_applied"] is False
        assert data["ttl_stopped_count"] == 0

    def test_ttl_cleanup_multiple_expired_sandboxes(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        auth_headers_with_workspace: dict,
        provider_singleton: LocalComposeSandboxProvider,
    ):
        """Multiple TTL-expired sandboxes should all be stopped."""
        workspace_id = str(workspace_alpha.id)

        # Create multiple expired sandboxes
        repo = SandboxInstanceRepository(db_session)
        expired_ids = []
        for i in range(3):
            sandbox = repo.create(
                workspace_id=workspace_alpha.id,
                profile=SandboxProfile.LOCAL_COMPOSE,
                idle_ttl_seconds=300,
            )
            sandbox.last_activity_at = datetime.utcnow() - timedelta(minutes=10 + i)
            sandbox.state = SandboxState.ACTIVE
            sandbox.health_status = SandboxHealthStatus.HEALTHY
            sandbox.provider_ref = f"test-ref-{i}"
            expired_ids.append(str(sandbox.id))

            # Register in provider
            _register_sandbox_in_provider(
                provider=provider_singleton,
                workspace_id=workspace_alpha.id,
                provider_ref=sandbox.provider_ref,
                last_activity_minutes_ago=10 + i,
            )

        db_session.commit()

        # Call resolve endpoint
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )

        # Should stop all expired sandboxes and provision new one
        assert response.status_code == 200
        data = response.json()
        assert data["ttl_cleanup_applied"] is True
        assert data["ttl_stopped_count"] == 3
        assert len(data["ttl_stopped_ids"]) == 3
        for expired_id in expired_ids:
            assert expired_id in data["ttl_stopped_ids"]


class TestTTLObservabilityInResponse:
    """Test that TTL cleanup is observable in API responses."""

    def test_response_contains_ttl_metadata(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """Resolve response should contain TTL cleanup metadata."""
        workspace_id = str(workspace_alpha.id)

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )

        assert response.status_code == 200
        data = response.json()

        # All TTL fields should be present
        assert "ttl_cleanup_applied" in data
        assert "ttl_stopped_count" in data
        assert "ttl_stopped_ids" in data
        assert "ttl_cleanup_reason" in data

        # When cleanup is applied
        if data["ttl_cleanup_applied"]:
            assert data["ttl_stopped_count"] > 0
            assert data["ttl_stopped_ids"] is not None
            assert len(data["ttl_stopped_ids"]) == data["ttl_stopped_count"]
            assert data["ttl_cleanup_reason"] is not None
            assert len(data["ttl_cleanup_reason"]) > 0

    def test_no_cleanup_defaults(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        active_recent_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """When no TTL cleanup is applied, defaults should be sensible."""
        workspace_id = str(workspace_alpha.id)

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["ttl_cleanup_applied"] is False
        assert data["ttl_stopped_count"] == 0
        assert data["ttl_stopped_ids"] is None or len(data["ttl_stopped_ids"]) == 0


class TestTTLPersistence:
    """Test that TTL state transitions are durably persisted."""

    def test_expired_sandbox_ttl_cleanup_triggers(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """TTL-expired sandbox should trigger cleanup and be marked stopped in DB."""
        workspace_id = str(workspace_alpha.id)
        expired_id = str(expired_sandbox.id)

        # Resolve triggers TTL cleanup
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )
        assert response.status_code == 200
        data = response.json()

        # TTL cleanup should be applied
        assert data["ttl_cleanup_applied"] is True
        assert data["ttl_stopped_count"] >= 1
        assert expired_id in (data["ttl_stopped_ids"] or [])

        # Verify in database that expired sandbox is stopped
        db_session.refresh(expired_sandbox)
        assert expired_sandbox.state == SandboxState.STOPPED

    def test_db_state_reflects_ttl_transitions(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """Database should reflect TTL stop transitions with proper state."""
        workspace_id = str(workspace_alpha.id)
        expired_id = str(expired_sandbox.id)

        # Pre-condition: sandbox is active
        db_session.refresh(expired_sandbox)
        assert expired_sandbox.state == SandboxState.ACTIVE
        assert expired_sandbox.health_status == SandboxHealthStatus.HEALTHY

        # Trigger TTL cleanup
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify TTL cleanup was applied
        assert data["ttl_cleanup_applied"] is True
        assert expired_id in (data["ttl_stopped_ids"] or [])

        # Post-condition: sandbox is stopped in DB
        db_session.refresh(expired_sandbox)
        assert expired_sandbox.state == SandboxState.STOPPED

    def test_cross_request_durability(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """TTL state must survive separate HTTP request boundaries."""
        workspace_id = str(workspace_alpha.id)
        str(expired_sandbox.id)

        # Request 1: Trigger TTL cleanup
        response1 = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ttl_cleanup_applied"] is True

        # Verify in DB: original sandbox is stopped (durability across request boundary)
        db_session.refresh(expired_sandbox)
        assert expired_sandbox.state == SandboxState.STOPPED


class TestTTLStopAndReplaceBehavior:
    """Test complete stop-and-replace behavior with persisted assertions."""

    def test_stop_and_replace_flow(
        self,
        client,
        db_session: Session,
        workspace_alpha: Workspace,
        expired_sandbox: SandboxInstance,
        auth_headers_with_workspace: dict,
    ):
        """Complete flow: expired sandbox stopped, replacement provisioned, state persisted."""
        workspace_id = str(workspace_alpha.id)
        expired_id = str(expired_sandbox.id)

        # Initial state: one expired active sandbox
        repo = SandboxInstanceRepository(db_session)
        initial_sandboxes = repo.list_by_workspace(workspace_alpha.id, include_inactive=False)
        assert len(initial_sandboxes) == 1
        assert str(initial_sandboxes[0].id) == expired_id

        # Call resolve - should stop expired and provision replacement
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sandbox/resolve",
            headers=auth_headers_with_workspace,
        )
        assert response.status_code == 200
        data = response.json()

        # Response assertions
        assert data["ttl_cleanup_applied"] is True
        assert data["ttl_stopped_count"] == 1
        assert expired_id in data["ttl_stopped_ids"]
        assert data["sandbox_id"] is not None
        assert data["sandbox_id"] != expired_id

        # DB assertions
        db_session.commit()

        # Expired sandbox is now stopped
        expired_db = repo.get_by_id(UUID(expired_id))
        assert expired_db.state == SandboxState.STOPPED

        # New sandbox is active
        new_sandbox = repo.get_by_id(UUID(data["sandbox_id"]))
        assert new_sandbox is not None
        assert new_sandbox.state == SandboxState.ACTIVE
        assert new_sandbox.workspace_id == workspace_alpha.id

        # Active sandbox count is back to 1 (replacement created)
        final_active = repo.list_by_workspace(workspace_alpha.id, include_inactive=False)
        assert len(final_active) == 1
        assert str(final_active[0].id) == data["sandbox_id"]
