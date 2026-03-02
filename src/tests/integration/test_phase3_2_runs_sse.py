"""Tests for OSS SSE event helper."""

import json
import pytest

from src.services.oss_sse_events import (
    OssSseEvent,
    OssSseEventBuilder,
    OssEventType,
    sanitize_error_for_user,
)


class TestOssSseEvent:
    """Test OssSseEvent data class."""

    def test_to_sse_dict(self):
        """Test conversion to SSE dict format."""
        event = OssSseEvent(
            id="run-1:1",
            type=OssEventType.MESSAGE,
            ts=1234567890.0,
            run_id="run-1",
            data={"role": "assistant", "content": "Hello"},
        )

        result = event.to_sse_dict()

        assert result["id"] == "run-1:1"
        assert result["event"] == "message"
        # Data should be JSON string
        data = json.loads(result["data"])
        assert data["ts"] == 1234567890.0
        assert data["run_id"] == "run-1"
        assert data["data"]["content"] == "Hello"

    def test_to_sse_lines(self):
        """Test conversion to SSE lines format."""
        event = OssSseEvent(
            id="run-1:1",
            type=OssEventType.QUEUED,
            ts=1234567890.0,
            run_id="run-1",
            data={"position": 1},
        )

        lines = event.to_sse_lines()

        assert "id: run-1:1" in lines
        assert "event: queued" in lines
        assert "data:" in lines
        assert lines.endswith("\n\n")  # Empty line terminates event


class TestOssSseEventBuilder:
    """Test OssSseEventBuilder factory methods."""

    @pytest.fixture
    def builder(self):
        """Create event builder."""
        return OssSseEventBuilder("run-123")

    def test_queued_event(self, builder):
        """Test queued event creation."""
        event = builder.queued(position=2)

        assert event.type == OssEventType.QUEUED
        assert event.run_id == "run-123"
        assert event.data["position"] == 2
        assert event.id.startswith("run-123:")

    def test_provisioning_event(self, builder):
        """Test provisioning event creation."""
        event = builder.provisioning(
            step="sandbox_create",
            message="Creating sandbox..."
        )

        assert event.type == OssEventType.PROVISIONING
        assert event.data["step"] == "sandbox_create"
        assert event.data["message"] == "Creating sandbox..."

    def test_running_event(self, builder):
        """Test running event creation."""
        event = builder.running(step="bridge_execute")

        assert event.type == OssEventType.RUNNING
        assert event.data["step"] == "bridge_execute"

    def test_completed_event(self, builder):
        """Test completed event creation."""
        event = builder.completed(tokens_used=150)

        assert event.type == OssEventType.COMPLETED
        assert event.data["tokens_used"] == 150

    def test_failed_event(self, builder):
        """Test failed event creation."""
        event = builder.failed(
            error="Something went wrong",
            error_category="provisioning_failed"
        )

        assert event.type == OssEventType.FAILED
        assert event.data["error"] == "Something went wrong"
        assert event.data["category"] == "provisioning_failed"

    def test_message_event(self, builder):
        """Test message event creation."""
        event = builder.message(
            role="assistant",
            content="Hello, world!"
        )

        assert event.type == OssEventType.MESSAGE
        assert event.data["role"] == "assistant"
        assert event.data["content"] == "Hello, world!"

    def test_tool_call_event(self, builder):
        """Test tool_call event creation."""
        event = builder.tool_call(
            tool_id="call-1",
            name="search",
            arguments={"query": "test"}
        )

        assert event.type == OssEventType.TOOL_CALL
        assert event.data["tool_id"] == "call-1"
        assert event.data["name"] == "search"
        assert event.data["arguments"]["query"] == "test"

    def test_tool_result_event(self, builder):
        """Test tool_result event creation."""
        event = builder.tool_result(
            tool_id="call-1",
            result={"status": "ok"}
        )

        assert event.type == OssEventType.TOOL_RESULT
        assert event.data["tool_id"] == "call-1"
        assert event.data["result"]["status"] == "ok"

    def test_ui_patch_event(self, builder):
        """Test ui_patch event creation."""
        event = builder.ui_patch(
            patch={"action": "update", "target": "header"}
        )

        assert event.type == OssEventType.UI_PATCH
        assert event.data["patch"]["action"] == "update"

    def test_state_update_event(self, builder):
        """Test state_update event creation."""
        event = builder.state_update(
            state={"counter": 42}
        )

        assert event.type == OssEventType.STATE_UPDATE
        assert event.data["state"]["counter"] == 42

    def test_error_event(self, builder):
        """Test error event creation."""
        event = builder.error(
            message="Rate limit exceeded",
            category="rate_limited",
            retryable=True
        )

        assert event.type == OssEventType.ERROR
        assert event.data["message"] == "Rate limit exceeded"
        assert event.data["category"] == "rate_limited"
        assert event.data["retryable"] is True

    def test_sequence_numbers_increment(self, builder):
        """Test that sequence numbers increment."""
        event1 = builder.queued()
        event2 = builder.running()
        event3 = builder.completed()

        # Sequence numbers should be 1, 2, 3
        assert event1.id == "run-123:1"
        assert event2.id == "run-123:2"
        assert event3.id == "run-123:3"

    def test_timestamps_set(self, builder):
        """Test that timestamps are set."""
        import time
        before = time.time()
        event = builder.queued()
        after = time.time()

        assert before <= event.ts <= after


class TestSanitizeErrorForUser:
    """Test error sanitization."""

    def test_sanitizes_tokens(self):
        """Test that tokens are redacted."""
        error = "Authentication failed with token=sk-live-1234567890abcdef"
        result = sanitize_error_for_user(error)

        assert "[REDACTED]" in result["message"]
        assert "sk-live-1234567890abcdef" not in result["message"]

    def test_sanitizes_bearer_tokens(self):
        """Test that bearer tokens are redacted."""
        error = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize_error_for_user(error)

        assert "[REDACTED]" in result["message"]
        assert "eyJhbGci" not in result["message"]

    def test_sanitizes_api_keys(self):
        """Test that API keys are redacted."""
        error = "Invalid api_key=sk-abc123def456ghi789"
        result = sanitize_error_for_user(error)

        assert "[REDACTED]" in result["message"]
        assert "sk-abc" not in result["message"]

    def test_sanitizes_urls_with_credentials(self):
        """Test that URLs with credentials are sanitized."""
        error = "Failed to connect to https://user:pass@example.com/api"
        result = sanitize_error_for_user(error)

        assert "[REDACTED]" in result["message"]
        assert "user:pass" not in result["message"]

    def test_sanitizes_uuids(self):
        """Test that UUIDs are redacted."""
        error = "Workspace 550e8400-e29b-41d4-a716-446655440000 not found"
        result = sanitize_error_for_user(error)

        assert "[ID]" in result["message"]
        assert "550e8400" not in result["message"]

    def test_preserves_safe_message(self):
        """Test that safe messages are preserved."""
        error = "Sandbox is not ready yet"
        result = sanitize_error_for_user(error)

        assert result["message"] == "Sandbox is not ready yet"

    def test_category_mapping(self):
        """Test error category mapping."""
        result = sanitize_error_for_user("Error", category="sandbox_provision_failed")
        assert result["category"] == "provisioning_failed"

        result = sanitize_error_for_user("Error", category="rate_limited")
        assert result["category"] == "rate_limited"

        result = sanitize_error_for_user("Error", category="unknown_error")
        assert result["category"] == "unknown_error"

    def test_handles_exception(self):
        """Test sanitization of exception objects."""
        error = ValueError("Something went wrong")
        result = sanitize_error_for_user(error)

        assert "Something went wrong" in result["message"]

    def test_handles_dict(self):
        """Test sanitization of dict errors."""
        error = {"message": "Failed", "code": 500}
        result = sanitize_error_for_user(error)

        assert "Failed" in result["message"]
