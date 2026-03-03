"""Tests for RunService lease release behavior."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

import pytest

from src.runtime_policy.models import EgressPolicy, SecretScope, ToolPolicy
from src.services.run_service import RunService, RunRoutingResult, RoutingErrorType


@pytest.mark.asyncio
async def test_execute_with_routing_releases_lease_on_routing_failure():
    """Routing failures with acquired lease release the lease immediately."""
    service = RunService()
    workspace_id = str(uuid4())
    run_id = str(uuid4())

    service.resolve_routing_target = AsyncMock(
        return_value=RunRoutingResult(
            success=False,
            workspace_id=workspace_id,
            lease_acquired=True,
            error_type=RoutingErrorType.ROUTING_FAILED,
            error="routing failed",
            run_id=run_id,
        )
    )

    lease_repo = MagicMock()

    with patch(
        "src.db.repositories.workspace_lease_repository.WorkspaceLeaseRepository",
        return_value=lease_repo,
    ):
        result = await service.execute_with_routing(
            principal=MagicMock(),
            session=MagicMock(),
            egress_policy=EgressPolicy.allow_all(),
            tool_policy=ToolPolicy.allow_all(),
            secret_policy=SecretScope.allow_all(),
            secrets={},
            input_message="hello",
        )

    assert result.status == "error"
    assert result.run_id == run_id
    lease_repo.release_lease.assert_called_once_with(
        workspace_id=UUID(workspace_id),
        holder_run_id=run_id,
    )
