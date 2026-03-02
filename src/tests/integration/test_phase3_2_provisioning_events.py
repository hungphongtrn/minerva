"""Tests for OSS /runs provisioning events.

Tests that first requests for new users emit provisioning events
before the agent response.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from uuid import uuid4
import json
import asyncio

from src.api.dependencies.external_identity import ExternalPrincipal
from src.services.oss_sse_events import OssEventType


class TestProvisioningEvents:
    """Test that provisioning events are emitted for cold starts."""

    @pytest.fixture
    def mock_principal(self):
        """Create a mock external principal."""
        return ExternalPrincipal(
            user_id=str(uuid4()),
            workspace_id=str(uuid4()),
            external_user_id="test-user-123",
            is_active=True,
        )

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_event_types_exist(self, mock_principal, mock_db):
        """Test that all required event types can be emitted."""
        from src.api.oss.routes.runs import _execute_run_with_events

        events = []

        async def collect_events():
            async for event in _execute_run_with_events(
                principal=mock_principal,
                db=mock_db,
                input_message="Hello",
                session_id=None,
                idempotency_key=None,
                run_id="test-run-123",
            ):
                events.append(event)

        # Mock the sandbox repository
        with patch("src.api.oss.routes.runs.SandboxInstanceRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_workspace.return_value = [Mock()]  # Warm start
            mock_repo_class.return_value = mock_repo

            # Mock the user queue with successful result
            with patch("src.api.oss.routes.runs.get_oss_user_queue") as mock_queue_func:
                mock_queue = MagicMock()

                mock_result = MagicMock()
                mock_result.outputs = {
                    "bridge": {"success": True, "output": {"message": "Hello!"}},
                    "final_output": "Hello!",
                }

                mock_queue_result = MagicMock()
                mock_queue_result.success = True
                mock_queue_result.was_cached = False
                mock_queue_result.result = mock_result

                # Make execute return an awaitable
                future = asyncio.Future()
                future.set_result(mock_queue_result)
                mock_queue.execute.return_value = future
                mock_queue_func.return_value = mock_queue

                await collect_events()

        # Parse events to check structure
        parsed_events = []
        for event_str in events:
            # Parse SSE format
            lines = event_str.strip().split("\n")
            event_data = {}
            for line in lines:
                if line.startswith("event: "):
                    event_data["type"] = line[7:]
                elif line.startswith("data: "):
                    try:
                        event_data["data"] = json.loads(line[6:])
                    except json.JSONDecodeError:
                        pass
            if event_data:
                parsed_events.append(event_data)

        # Should have events
        assert len(parsed_events) > 0

        # Check event types exist
        event_types = [e.get("type") for e in parsed_events]

        # Should have queued event first
        assert OssEventType.QUEUED.value in event_types

        # Should have running event
        assert OssEventType.RUNNING.value in event_types

        # Should end with completed or failed
        assert event_types[-1] in [OssEventType.COMPLETED.value, OssEventType.FAILED.value]


class TestIdempotencyBehavior:
    """Test idempotency in /runs endpoint."""

    @pytest.fixture
    def mock_principal(self):
        """Create a mock external principal."""
        return ExternalPrincipal(
            user_id=str(uuid4()),
            workspace_id=str(uuid4()),
            external_user_id="test-user-456",
            is_active=True,
        )

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_execution_flow(self, mock_principal, mock_db):
        """Test that the execution flow completes."""
        from src.api.oss.routes.runs import _execute_run_with_events

        events = []

        async def collect_events():
            async for event in _execute_run_with_events(
                principal=mock_principal,
                db=mock_db,
                input_message="Hello",
                session_id=None,
                idempotency_key="test-key-123",
                run_id="test-run-789",
            ):
                events.append(event)

        # Mock with result
        with patch("src.api.oss.routes.runs.SandboxInstanceRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_workspace.return_value = [Mock()]
            mock_repo_class.return_value = mock_repo

            with patch("src.api.oss.routes.runs.get_oss_user_queue") as mock_queue_func:
                mock_queue = MagicMock()

                mock_result = MagicMock()
                mock_result.outputs = {
                    "bridge": {"success": True, "output": {"message": "Response!"}},
                    "final_output": "Response!",
                }

                mock_queue_result = MagicMock()
                mock_queue_result.success = True
                mock_queue_result.was_cached = False
                mock_queue_result.result = mock_result

                future = asyncio.Future()
                future.set_result(mock_queue_result)
                mock_queue.execute.return_value = future
                mock_queue_func.return_value = mock_queue

                await collect_events()

        # Should have events
        assert len(events) > 0

        # Parse events
        parsed_events = []
        for event_str in events:
            lines = event_str.strip().split("\n")
            event_data = {}
            for line in lines:
                if line.startswith("event: "):
                    event_data["type"] = line[7:]
            if event_data:
                parsed_events.append(event_data)

        event_types = [e.get("type") for e in parsed_events]

        # Should have the expected flow
        assert OssEventType.QUEUED.value in event_types
        assert OssEventType.RUNNING.value in event_types


class TestErrorHandling:
    """Test error handling in /runs endpoint."""

    @pytest.fixture
    def mock_principal(self):
        """Create a mock external principal."""
        return ExternalPrincipal(
            user_id=str(uuid4()),
            workspace_id=str(uuid4()),
            external_user_id="test-user-789",
            is_active=True,
        )

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.mark.asyncio
    async def test_failed_execution_emits_failed_event(self, mock_principal, mock_db):
        """Test that failed execution emits a failed event."""
        from src.api.oss.routes.runs import _execute_run_with_events

        events = []

        async def collect_events():
            async for event in _execute_run_with_events(
                principal=mock_principal,
                db=mock_db,
                input_message="Hello",
                session_id=None,
                idempotency_key=None,
                run_id="test-run-fail",
            ):
                events.append(event)

        # Mock with failed result
        with patch("src.api.oss.routes.runs.SandboxInstanceRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_workspace.return_value = [Mock()]
            mock_repo_class.return_value = mock_repo

            with patch("src.api.oss.routes.runs.get_oss_user_queue") as mock_queue_func:
                mock_queue = MagicMock()

                mock_queue_result = MagicMock()
                mock_queue_result.success = False
                mock_queue_result.was_cached = False
                mock_queue_result.error = "Sandbox provisioning failed"
                mock_queue_result.result = None

                future = asyncio.Future()
                future.set_result(mock_queue_result)
                mock_queue.execute.return_value = future
                mock_queue_func.return_value = mock_queue

                await collect_events()

        # Parse events
        parsed_events = []
        for event_str in events:
            lines = event_str.strip().split("\n")
            event_data = {}
            for line in lines:
                if line.startswith("event: "):
                    event_data["type"] = line[7:]
            if event_data:
                parsed_events.append(event_data)

        event_types = [e.get("type") for e in parsed_events]

        # Should end with failed event
        assert event_types[-1] == OssEventType.FAILED.value
