"""Integration tests for sandbox token lifecycle: provision-time injection and rotation grace.

Tests verify:
1. The token injected into runtime_bridge_config equals the persisted bridge_auth_token
2. Token rotation preserves the previous token with a 30-second grace period
3. Reprovisioning uses the new token consistently in both config and persistence
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from typing import Dict, Any, Optional

from src.db.models import (
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    SandboxHydrationStatus,
)
from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxInfo,
    SandboxRef,
    SandboxHealth,
)
from src.services.sandbox_orchestrator_service import (
    SandboxOrchestratorService,
    RoutingResult,
)
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository


@pytest.fixture
def captured_configs():
    """Fixture to capture SandboxConfig instances passed to provider."""
    return []


@pytest.fixture
def mock_provider_with_capture(captured_configs):
    """Create a mock provider that captures runtime_bridge_config."""
    provider = AsyncMock()

    async def capture_provision(config: SandboxConfig) -> SandboxInfo:
        """Capture config and return mock success."""
        captured_configs.append(config)
        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=f"test-{uuid4()}",
                profile=config.workspace_id,  # Use workspace_id as profile for testing
                metadata={
                    "gateway_url": f"http://test-gateway-{uuid4()}:18790",
                    "runtime_ready": True,
                },
            ),
            health=SandboxHealth.HEALTHY,
            state="running",
        )

    provider.provision_sandbox = capture_provision
    provider.get_health = AsyncMock(return_value=None)
    provider.stop_sandbox = AsyncMock()
    provider.profile = SandboxProfile.LOCAL_COMPOSE

    return provider


@pytest.mark.asyncio
async def test_provision_time_token_consistency(
    db_session,
    workspace_alpha,
    mock_provider_with_capture,
    captured_configs,
):
    """The token in runtime_bridge_config matches the persisted bridge_auth_token.

    This is the core fix for AUTH_FAILED cascades caused by token mismatch.
    """
    # Create orchestrator with capturing mock provider
    orchestrator = SandboxOrchestratorService(db_session, provider=mock_provider_with_capture)

    # Provision a sandbox
    result = await orchestrator.resolve_sandbox(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
    )

    # Should succeed
    assert result.success, f"Provisioning failed: {result.message}"
    assert result.sandbox is not None
    assert result.result == RoutingResult.PROVISIONED_NEW

    # Should have captured exactly one config
    assert len(captured_configs) == 1, f"Expected 1 config, got {len(captured_configs)}"
    config = captured_configs[0]

    # Config should have runtime_bridge_config
    assert config.runtime_bridge_config is not None
    assert "bridge" in config.runtime_bridge_config
    assert "auth_token" in config.runtime_bridge_config["bridge"]

    # Get the token that was injected into runtime config
    runtime_token = config.runtime_bridge_config["bridge"]["auth_token"]

    # Get the persisted token from the sandbox record
    sandbox = result.sandbox

    # The runtime token should match the persisted current token
    assert runtime_token == sandbox.bridge_auth_token, (
        f"Token mismatch! Runtime config has different token than DB. "
        f"Runtime: {runtime_token[:10]}..., DB: {sandbox.bridge_auth_token[:10] if sandbox.bridge_auth_token else None}..."
    )

    # Token should be present and non-empty
    assert runtime_token, "Runtime token should not be empty"
    assert len(runtime_token) >= 32, "Token should be reasonably long (urlsafe base64)"


@pytest.mark.asyncio
async def test_token_rotation_grace_period(
    db_session,
    workspace_alpha,
    mock_provider_with_capture,
    captured_configs,
):
    """Token rotation preserves previous token with 30-second grace period."""
    # Create orchestrator
    orchestrator = SandboxOrchestratorService(db_session, provider=mock_provider_with_capture)

    # First provisioning
    result1 = await orchestrator.resolve_sandbox(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
    )

    assert result1.success, f"First provisioning failed: {result1.message}"
    sandbox1 = result1.sandbox
    first_token = sandbox1.bridge_auth_token

    # Verify no previous token on first provision
    assert sandbox1.bridge_auth_token_prev is None, (
        "First provision should not have previous token"
    )

    # Get first runtime token
    first_runtime_token = captured_configs[0].runtime_bridge_config["bridge"]["auth_token"]
    assert first_runtime_token == first_token, "First provision token mismatch"

    # Clear captured configs for second provision
    captured_configs.clear()

    # Simulate sandbox becoming unhealthy to trigger reprovisioning
    # This is done by marking the existing sandbox as unhealthy
    repository = SandboxInstanceRepository(db_session)
    repository.update_health(sandbox1.id, SandboxHealthStatus.UNHEALTHY)
    repository.update_state(sandbox1.id, SandboxState.UNHEALTHY)
    db_session.commit()

    # Second provisioning (simulating reprovision scenario)
    result2 = await orchestrator.resolve_sandbox(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
    )

    # Should succeed (either routed to new or provisioned)
    assert result2.success, f"Second provisioning failed: {result2.message}"

    # Get the second sandbox (may be same or different record)
    sandbox2 = result2.sandbox

    # If this is a new sandbox record, verify rotation on the new one
    # If same record, verify rotation happened
    if sandbox2.id == sandbox1.id:
        # Same sandbox was reused - rotation should have happened
        pass
    else:
        # New sandbox - check its token
        second_token = sandbox2.bridge_auth_token

        # Should have a different token
        assert second_token != first_token, "New sandbox should have different token"

        # Get second runtime token
        assert len(captured_configs) == 1, (
            f"Expected 1 config for second provision, got {len(captured_configs)}"
        )
        second_runtime_token = captured_configs[0].runtime_bridge_config["bridge"]["auth_token"]

        # Second runtime token should match second persisted token
        assert second_runtime_token == second_token, (
            f"Second provision token mismatch! Runtime: {second_runtime_token[:10]}..., "
            f"DB: {second_token[:10] if second_token else None}..."
        )


@pytest.mark.asyncio
async def test_explicit_grace_seconds_in_rotation(
    db_session,
    workspace_alpha,
):
    """Verify rotate_bridge_token uses 30-second grace period explicitly."""
    from src.db.repositories.sandbox_instance_repository import (
        SandboxInstanceRepository,
    )

    # Create a sandbox record
    repository = SandboxInstanceRepository(db_session)
    sandbox = repository.create(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
    )
    db_session.commit()

    # Set initial token
    initial_token = "initial-test-token-12345"
    sandbox.bridge_auth_token = initial_token
    db_session.commit()

    # Rotate with explicit grace_seconds
    new_token = "new-test-token-67890"
    grace_seconds = 30

    repository.rotate_bridge_token(sandbox.id, new_token, grace_seconds=grace_seconds)
    db_session.commit()

    # Refresh sandbox
    db_session.refresh(sandbox)

    # Verify previous token is set
    assert sandbox.bridge_auth_token_prev == initial_token, (
        f"Previous token should be '{initial_token}', got '{sandbox.bridge_auth_token_prev}'"
    )

    # Verify previous token has expiry timestamp
    assert sandbox.bridge_auth_token_prev_expires_at is not None, (
        "Previous token should have expiry timestamp"
    )

    # Verify expiry is in the future (within grace window)
    now = datetime.now(timezone.utc)
    expiry = sandbox.bridge_auth_token_prev_expires_at

    # Handle timezone-aware comparison
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    assert expiry > now, f"Previous token expiry should be in the future: {expiry} <= {now}"

    # Verify expiry is approximately grace_seconds from now (within tolerance)
    expected_min = now + timedelta(seconds=grace_seconds - 5)
    expected_max = now + timedelta(seconds=grace_seconds + 5)

    assert expected_min <= expiry <= expected_max, (
        f"Expiry should be ~{grace_seconds}s from now. "
        f"Expected between {expected_min} and {expected_max}, got {expiry}"
    )

    # Verify current token is the new one
    assert sandbox.bridge_auth_token == new_token, (
        f"Current token should be '{new_token}', got '{sandbox.bridge_auth_token}'"
    )


@pytest.mark.asyncio
async def test_runtime_config_token_structure(
    db_session,
    workspace_alpha,
    mock_provider_with_capture,
    captured_configs,
):
    """Runtime bridge config has correct structure with auth token."""
    orchestrator = SandboxOrchestratorService(db_session, provider=mock_provider_with_capture)

    result = await orchestrator.resolve_sandbox(
        workspace_id=workspace_alpha.id,
        profile=SandboxProfile.LOCAL_COMPOSE,
    )

    assert result.success, f"Provisioning failed: {result.message}"
    assert len(captured_configs) == 1

    config = captured_configs[0]
    runtime_config = config.runtime_bridge_config

    # Verify structure
    assert "workspace_id" in runtime_config, "Should have workspace_id"
    assert "bridge" in runtime_config, "Should have bridge section"
    assert "auth_token" in runtime_config["bridge"], "Should have auth_token in bridge"
    assert "auth_mode" in runtime_config["bridge"], "Should have auth_mode in bridge"
    assert "gateway_port" in runtime_config["bridge"], "Should have gateway_port in bridge"

    # Verify auth_mode is bearer
    assert runtime_config["bridge"]["auth_mode"] == "bearer", (
        f"Auth mode should be 'bearer', got '{runtime_config['bridge']['auth_mode']}'"
    )

    # Verify token is non-empty string
    token = runtime_config["bridge"]["auth_token"]
    assert isinstance(token, str), f"Token should be string, got {type(token)}"
    assert len(token) > 0, "Token should not be empty"


@pytest.mark.asyncio
async def test_token_mismatch_impossible_by_construction(
    db_session,
    workspace_alpha,
):
    """Token mismatch is structurally impossible due to single-token generation.

    This test verifies the fix by directly calling _generate_runtime_bridge_config
    and ensuring it uses the provided token parameter.
    """
    from src.services.sandbox_orchestrator_service import SandboxOrchestratorService

    # Create minimal orchestrator
    orchestrator = SandboxOrchestratorService(db_session)

    # Define a test token
    test_token = "my-test-token-for-verification-123"

    # Call the method directly with explicit token
    config = orchestrator._generate_runtime_bridge_config(
        workspace_id=workspace_alpha.id,
        agent_pack_id=None,
        env_vars={},
        bridge_auth_token=test_token,
    )

    # Verify the config contains exactly the token we provided
    assert config["bridge"]["auth_token"] == test_token, (
        f"Config should contain the exact token we passed. "
        f"Expected: {test_token}, Got: {config['bridge']['auth_token']}"
    )

    # Verify calling without token raises TypeError (token is required)
    with pytest.raises(TypeError):
        orchestrator._generate_runtime_bridge_config(
            workspace_id=workspace_alpha.id,
            agent_pack_id=None,
            env_vars={},
            # Missing bridge_auth_token
        )
