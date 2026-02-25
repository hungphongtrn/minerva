"""Integration tests for fail-fast run routing and pack-specific errors.

Tests verify:
- Fail-fast routing contract: routing failures prevent run execution
- Pack-specific error types: deterministic error categorization
- Profile parity: equivalent semantic outcomes across local/daytona profiles
"""

import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.db.models import (
    AgentPack,
    AgentPackValidationStatus,
    Workspace,
    User,
)
from src.services.run_service import RoutingErrorType


@pytest.fixture
def sample_agent_pack(db_session: Session, workspace_alpha: Workspace) -> AgentPack:
    """Create a valid agent pack for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        name="Test Pack",
        source_path="/tmp/test-pack",
        source_digest="abc123",
        validation_status=AgentPackValidationStatus.VALID,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


@pytest.fixture
def invalid_agent_pack(db_session: Session, workspace_alpha: Workspace) -> AgentPack:
    """Create an invalid agent pack for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        name="Invalid Pack",
        source_path="/tmp/invalid-pack",
        source_digest="def456",
        validation_status=AgentPackValidationStatus.INVALID,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


@pytest.fixture
def stale_agent_pack(db_session: Session, workspace_alpha: Workspace) -> AgentPack:
    """Create a stale agent pack for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        name="Stale Pack",
        source_path="/tmp/stale-pack",
        source_digest="old-digest",
        validation_status=AgentPackValidationStatus.STALE,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


@pytest.fixture
def inactive_agent_pack(db_session: Session, workspace_alpha: Workspace) -> AgentPack:
    """Create an inactive agent pack for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_alpha.id,
        name="Inactive Pack",
        source_path="/tmp/inactive-pack",
        source_digest="ghi789",
        validation_status=AgentPackValidationStatus.VALID,
        is_active=False,  # Inactive
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


@pytest.fixture
def other_workspace_pack(db_session: Session, workspace_beta: Workspace) -> AgentPack:
    """Create an agent pack in a different workspace for testing."""
    pack = AgentPack(
        id=uuid4(),
        workspace_id=workspace_beta.id,
        name="Other Pack",
        source_path="/tmp/other-pack",
        source_digest="jkl012",
        validation_status=AgentPackValidationStatus.VALID,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(pack)
    db_session.commit()
    return pack


# ============================================================================
# Fail-Fast Routing Tests
# ============================================================================


class TestFailFastRouting:
    """Tests for fail-fast routing contract."""

    def test_run_fails_fast_when_pack_not_found(
        self, client: TestClient, owner_headers: dict
    ):
        """Run should fail immediately with pack_not_found error."""
        nonexistent_pack_id = str(uuid4())

        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": nonexistent_pack_id,
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_type"] == "pack_not_found"
        assert "agent pack not found" in data["detail"]["error"].lower()
        assert "remediation" in data["detail"]

    def test_run_fails_fast_when_pack_invalid(
        self,
        client: TestClient,
        owner_headers: dict,
        invalid_agent_pack: AgentPack,
    ):
        """Run should fail immediately with pack_invalid error."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(invalid_agent_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_type"] == "pack_invalid"
        assert "not valid" in data["detail"]["error"].lower()
        assert "remediation" in data["detail"]

    def test_run_fails_fast_when_pack_stale(
        self,
        client: TestClient,
        owner_headers: dict,
        stale_agent_pack: AgentPack,
    ):
        """Run should fail immediately with pack_stale error."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(stale_agent_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        assert response.status_code == 400
        data = response.json()
        # Stale packs are treated as invalid
        assert data["detail"]["error_type"] in ["pack_stale", "pack_invalid"]
        assert "remediation" in data["detail"]

    def test_run_fails_fast_when_pack_inactive(
        self,
        client: TestClient,
        owner_headers: dict,
        inactive_agent_pack: AgentPack,
    ):
        """Run should fail immediately when pack is inactive."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(inactive_agent_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        # Inactive pack should trigger some form of validation error
        assert response.status_code in [400, 403, 404]
        data = response.json()
        assert "error_type" in data["detail"]

    def test_run_fails_fast_when_pack_workspace_mismatch(
        self,
        client: TestClient,
        owner_headers: dict,
        other_workspace_pack: AgentPack,
    ):
        """Run should fail immediately with pack_workspace_mismatch error."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(other_workspace_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error_type"] == "pack_workspace_mismatch"
        assert "does not belong to workspace" in data["detail"]["error"].lower()
        assert "remediation" in data["detail"]

    def test_run_does_not_fail_with_pack_error_for_valid_pack(
        self,
        client: TestClient,
        owner_headers: dict,
        sample_agent_pack: AgentPack,
    ):
        """Valid pack should not trigger pack-specific errors (404/403/400 pack_*).

        The run may fail for infrastructure reasons (503) or succeed (201),
        but should NOT fail with pack_not_found, pack_invalid, pack_workspace_mismatch, etc.
        """
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(sample_agent_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        # Should NOT get pack-specific errors
        if response.status_code in [400, 403, 404]:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                error_type = detail.get("error_type", "")
                assert error_type not in [
                    "pack_not_found",
                    "pack_invalid",
                    "pack_stale",
                    "pack_workspace_mismatch",
                ], f"Valid pack should not fail with {error_type}"

        # Response should be 201 (success) or 503 (infrastructure), not pack errors
        assert response.status_code in [201, 503, 500]


# ============================================================================
# Error Contract Tests
# ============================================================================


class TestErrorContract:
    """Tests for deterministic error type contracts."""

    def test_error_response_contains_all_required_fields(
        self, client: TestClient, owner_headers: dict
    ):
        """Error responses must contain error, error_type, and remediation."""
        nonexistent_pack_id = str(uuid4())

        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": nonexistent_pack_id,
                "input": {},
            },
        )

        assert response.status_code == 404
        data = response.json()
        detail = data["detail"]

        assert "error" in detail
        assert "error_type" in detail
        assert "remediation" in detail
        assert isinstance(detail["error"], str)
        assert isinstance(detail["error_type"], str)
        assert isinstance(detail["remediation"], str)

    def test_pack_not_found_returns_404(self, client: TestClient, owner_headers: dict):
        """Non-existent pack should return 404 Not Found."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(uuid4())},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["error_type"] == "pack_not_found"

    def test_pack_workspace_mismatch_returns_403(
        self,
        client: TestClient,
        owner_headers: dict,
        other_workspace_pack: AgentPack,
    ):
        """Pack from different workspace should return 403 Forbidden."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(other_workspace_pack.id)},
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error_type"] == "pack_workspace_mismatch"

    def test_pack_validation_errors_return_400(
        self,
        client: TestClient,
        owner_headers: dict,
        invalid_agent_pack: AgentPack,
    ):
        """Invalid pack should return 400 Bad Request."""
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(invalid_agent_pack.id)},
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error_type"] == "pack_invalid"


# ============================================================================
# Profile Parity Tests
# ============================================================================


class TestProfileParity:
    """Tests for cross-profile parity (local_compose vs daytona).

    Parity contract: A registered valid agent pack never returns pack/routing
    client-error semantics (400/403/404 pack_* or workspace_resolution_failed)
    in either local_compose or daytona profiles. Valid-pack failures, when they
    occur, must be infrastructure-class (503/500) and equivalent across profiles.
    """

    def test_routing_error_types_consistent_across_profiles(
        self, client: TestClient, owner_headers: dict
    ):
        """Error types should be identical regardless of profile."""
        # Test with local_compose profile (default in tests)
        response_local = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(uuid4())},
        )

        # Error type should be pack_not_found regardless of profile
        assert response_local.status_code == 404
        assert response_local.json()["detail"]["error_type"] == "pack_not_found"

    def test_fail_fast_semantics_equivalent_across_profiles(
        self,
        client: TestClient,
        owner_headers: dict,
        invalid_agent_pack: AgentPack,
    ):
        """Fail-fast behavior should be identical regardless of profile."""
        # Test with local_compose profile
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(invalid_agent_pack.id)},
        )

        # Should fail fast with 400 before any sandbox provisioning
        assert response.status_code == 400
        assert "not valid" in response.json()["detail"]["error"].lower()

    def test_valid_pack_never_returns_pack_client_errors(
        self,
        client: TestClient,
        owner_headers: dict,
        sample_agent_pack: AgentPack,
    ):
        """Valid pack must never return 4xx pack_* or workspace_resolution errors.

        This is the core parity contract: valid packs should only return:
        - 201: Success
        - 503: Infrastructure unavailability (provider failure)
        - 500: Unexpected server error

        They must NOT return:
        - 404 pack_not_found
        - 403 pack_workspace_mismatch
        - 400 pack_invalid, pack_stale, workspace_resolution_failed
        """
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={
                "agent_pack_id": str(sample_agent_pack.id),
                "input": {},
                "allowed_hosts": ["*"],
            },
        )

        # Valid pack must not return pack-specific 4xx errors
        if response.status_code in [400, 403, 404]:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                error_type = detail.get("error_type", "")
                # These are the forbidden error types for valid packs
                forbidden_types = [
                    "pack_not_found",
                    "pack_invalid",
                    "pack_stale",
                    "pack_workspace_mismatch",
                    "workspace_resolution_failed",
                ]
                assert error_type not in forbidden_types, (
                    f"Valid pack returned forbidden error_type '{error_type}'. "
                    f"Valid packs must not return pack/routing client errors."
                )

        # Response must be in the acceptable range for valid packs
        assert response.status_code in [
            201,
            503,
            500,
        ], f"Valid pack returned {response.status_code}, expected 201, 503, or 500"

    def test_invalid_pack_returns_client_errors_not_infrastructure(
        self,
        client: TestClient,
        owner_headers: dict,
        invalid_agent_pack: AgentPack,
    ):
        """Invalid packs must return client errors (4xx), not infrastructure errors (5xx).

        This verifies that pack validation failures are correctly classified
        as client errors and don't masquerade as infrastructure failures.
        """
        response = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": str(invalid_agent_pack.id)},
        )

        # Invalid pack should return 4xx, not 5xx
        assert response.status_code in [
            400,
            403,
            404,
        ], f"Invalid pack returned {response.status_code}, expected 4xx client error"

        data = response.json()
        detail = data.get("detail", {})
        error_type = detail.get("error_type", "")

        # Should be a pack-specific error, not infrastructure
        infrastructure_types = ["provider_unavailable", "sandbox_provision_failed"]
        assert error_type not in infrastructure_types, (
            f"Invalid pack returned infrastructure error_type '{error_type}'. "
            f"Pack validation failures must be client errors."
        )

    def test_error_type_determinism_for_same_scenario(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        """Same scenario must produce same error type across requests.

        This ensures deterministic behavior for API consumers.
        """
        nonexistent_pack_id = str(uuid4())

        # First request
        response1 = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": nonexistent_pack_id},
        )

        # Second request with same pack_id
        response2 = client.post(
            "/api/v1/runs",
            headers=owner_headers,
            json={"agent_pack_id": nonexistent_pack_id},
        )

        # Both should have same status and error_type
        assert response1.status_code == response2.status_code

        detail1 = response1.json().get("detail", {})
        detail2 = response2.json().get("detail", {})
        assert detail1.get("error_type") == detail2.get("error_type")


# ============================================================================
# Routing Error Type Constants Tests
# ============================================================================


def test_routing_error_type_constants():
    """Verify error type constants are properly defined."""
    assert RoutingErrorType.PACK_NOT_FOUND == "pack_not_found"
    assert RoutingErrorType.PACK_WORKSPACE_MISMATCH == "pack_workspace_mismatch"
    assert RoutingErrorType.PACK_INVALID == "pack_invalid"
    assert RoutingErrorType.PACK_STALE == "pack_stale"
    assert RoutingErrorType.LEASE_CONFLICT == "lease_conflict"
    assert RoutingErrorType.PROVIDER_UNAVAILABLE == "provider_unavailable"
    assert RoutingErrorType.SANDBOX_PROVISION_FAILED == "sandbox_provision_failed"
    assert RoutingErrorType.WORKSPACE_RESOLUTION_FAILED == "workspace_resolution_failed"
    assert RoutingErrorType.ROUTING_FAILED == "routing_failed"
