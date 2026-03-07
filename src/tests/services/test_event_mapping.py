"""Unit tests for ZeroClaw to OSS SSE event mapping.

Tests the map_zeroclaw_event_to_oss_event helper to ensure:
1. Each supported upstream event type maps to the expected OssEventType
2. Unknown event types return None
3. Missing keys do not raise exceptions
"""

import pytest
from src.services.oss_sse_events import (
    OssSseEventBuilder,
    OssEventType,
    map_zeroclaw_event_to_oss_event,
)


class TestMapZeroclawEventToOssEvent:
    """Test cases for ZeroClaw upstream event mapping."""

    @pytest.fixture
    def builder(self):
        """Create a fresh OssSseEventBuilder for each test."""
        return OssSseEventBuilder(run_id="test-run-123")

    # =================================================================
    # Message Events
    # =================================================================

    def test_message_event_maps_to_message_type(self, builder):
        """message event should map to OssEventType.MESSAGE."""
        upstream = {
            "type": "message",
            "data": {"role": "assistant", "content": "Hello!"},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.MESSAGE
        assert event.data["role"] == "assistant"
        assert event.data["content"] == "Hello!"

    def test_message_delta_event_maps_to_message_type(self, builder):
        """message.delta event should map to OssEventType.MESSAGE."""
        upstream = {
            "type": "message.delta",
            "data": {"role": "assistant", "content": " partial"},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.MESSAGE
        assert event.data["content"] == " partial"

    def test_message_event_defaults_role_to_assistant(self, builder):
        """message event without role should default to assistant."""
        upstream = {"type": "message", "data": {"content": "Hello!"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["role"] == "assistant"

    def test_message_event_preserves_extra_fields(self, builder):
        """message event should preserve extra data fields."""
        upstream = {
            "type": "message",
            "data": {
                "role": "assistant",
                "content": "Hello!",
                "model": "claude-4",
                "tokens": 42,
            },
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["model"] == "claude-4"
        assert event.data["tokens"] == 42
        assert event.data["role"] == "assistant"  # role preserved in data
        assert event.data["content"] == "Hello!"  # content preserved in data

    # =================================================================
    # Tool Events
    # =================================================================

    def test_tool_call_event_maps_to_tool_call_type(self, builder):
        """tool.call event should map to OssEventType.TOOL_CALL."""
        upstream = {
            "type": "tool.call",
            "data": {
                "tool_id": "tool-123",
                "name": "search_web",
                "arguments": {"query": "python testing"},
            },
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.TOOL_CALL
        assert event.data["tool_id"] == "tool-123"
        assert event.data["name"] == "search_web"
        assert event.data["arguments"] == {"query": "python testing"}

    def test_tool_result_event_maps_to_tool_result_type(self, builder):
        """tool.result event should map to OssEventType.TOOL_RESULT."""
        upstream = {
            "type": "tool.result",
            "data": {
                "tool_id": "tool-123",
                "result": {"status": "success", "data": [1, 2, 3]},
            },
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.TOOL_RESULT
        assert event.data["tool_id"] == "tool-123"
        assert event.data["result"]["status"] == "success"

    def test_tool_call_defaults_empty_arguments(self, builder):
        """tool.call without arguments should default to empty dict."""
        upstream = {
            "type": "tool.call",
            "data": {"tool_id": "tool-123", "name": "test"},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["arguments"] == {}

    # =================================================================
    # UI/State Events
    # =================================================================

    def test_ui_patch_event_maps_to_ui_patch_type(self, builder):
        """ui.patch event should map to OssEventType.UI_PATCH."""
        upstream = {
            "type": "ui.patch",
            "data": {"patch": {"button": {"enabled": True, "text": "Click me"}}},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.UI_PATCH
        assert event.data["patch"]["button"]["enabled"] is True

    def test_state_update_event_maps_to_state_update_type(self, builder):
        """state.update event should map to OssEventType.STATE_UPDATE."""
        upstream = {
            "type": "state.update",
            "data": {"state": {"counter": 42, "user": "alice"}},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.STATE_UPDATE
        assert event.data["state"]["counter"] == 42

    def test_ui_patch_defaults_empty_patch(self, builder):
        """ui.patch without patch should default to empty dict."""
        upstream = {"type": "ui.patch", "data": {}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["patch"] == {}

    # =================================================================
    # Error Events (non-terminal)
    # =================================================================

    def test_error_event_maps_to_error_type(self, builder):
        """error event should map to OssEventType.ERROR."""
        upstream = {
            "type": "error",
            "data": {
                "message": "Rate limit exceeded",
                "category": "rate_limited",
                "retryable": True,
            },
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.ERROR
        assert event.data["message"] == "Rate limit exceeded"
        assert event.data["category"] == "rate_limited"
        assert event.data["retryable"] is True

    def test_error_event_defaults(self, builder):
        """error event should have sensible defaults."""
        upstream = {"type": "error", "data": {"message": "Something went wrong"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["category"] == "agent_error"
        assert event.data["retryable"] is False

    # =================================================================
    # Terminal Events
    # =================================================================

    def test_completed_event_maps_to_completed_type(self, builder):
        """completed event should map to OssEventType.COMPLETED."""
        upstream = {"type": "completed", "data": {"total_tokens": 150}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.COMPLETED
        assert event.data["total_tokens"] == 150

    def test_failed_event_maps_to_failed_type(self, builder):
        """failed event should map to OssEventType.FAILED."""
        upstream = {
            "type": "failed",
            "data": {"error": "LLM request timeout", "category": "timeout"},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.FAILED
        assert event.data["error"] == "LLM request timeout"
        assert event.data["category"] == "timeout"

    def test_failed_event_default_category(self, builder):
        """failed event without category should default to agent_error."""
        upstream = {"type": "failed", "data": {"error": "Unknown failure"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["category"] == "agent_error"

    # =================================================================
    # Unknown Event Types
    # =================================================================

    def test_unknown_event_type_returns_none(self, builder):
        """Unknown event types should return None safely."""
        upstream = {"type": "custom.unknown", "data": {"foo": "bar"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is None

    def test_empty_type_returns_none(self, builder):
        """Empty type should return None."""
        upstream = {"type": "", "data": {"foo": "bar"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is None

    def test_missing_type_returns_none(self, builder):
        """Missing type should return None."""
        upstream = {"data": {"foo": "bar"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is None

    # =================================================================
    # Robustness: Missing Keys
    # =================================================================

    def test_missing_data_defaults_to_empty_dict(self, builder):
        """Event without data field should use empty dict."""
        upstream = {"type": "message"}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.MESSAGE

    def test_none_data_treated_as_empty_dict(self, builder):
        """None data should be treated as empty dict."""
        upstream = {"type": "message", "data": None}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.MESSAGE

    def test_non_dict_data_treated_as_empty_dict(self, builder):
        """Non-dict data should be treated as empty dict."""
        upstream = {"type": "message", "data": "invalid"}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.MESSAGE

    def test_missing_keys_in_data_does_not_raise(self, builder):
        """Missing keys in data should not raise exceptions."""
        upstream = {
            "type": "tool.call",
            "data": {},  # Missing tool_id, name, arguments
        }
        # Should not raise
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.type == OssEventType.TOOL_CALL
        assert event.data["tool_id"] == ""
        assert event.data["name"] == ""
        assert event.data["arguments"] == {}

    # =================================================================
    # Event Sequencing
    # =================================================================

    def test_multiple_events_have_sequential_ids(self, builder):
        """Multiple events from same builder should have sequential IDs."""
        events_data = [
            {"type": "message", "data": {"content": "Hello"}},
            {"type": "tool.call", "data": {"tool_id": "t1", "name": "search"}},
            {"type": "tool.result", "data": {"tool_id": "t1", "result": "done"}},
            {"type": "completed", "data": {}},
        ]

        events = []
        for data in events_data:
            event = map_zeroclaw_event_to_oss_event(builder, data)
            if event:
                events.append(event)

        assert len(events) == 4
        # Check IDs are sequential
        ids = [e.id for e in events]
        assert ids == [
            "test-run-123:1",
            "test-run-123:2",
            "test-run-123:3",
            "test-run-123:4",
        ]

    def test_event_includes_run_id(self, builder):
        """All events should include the run_id from builder."""
        upstream = {"type": "message", "data": {"content": "Test"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.run_id == "test-run-123"

    def test_event_includes_timestamp(self, builder):
        """All events should include a timestamp."""
        upstream = {"type": "message", "data": {"content": "Test"}}
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert isinstance(event.ts, float)
        assert event.ts > 0


class TestMapZeroclawEventRobustness:
    """Additional robustness tests for edge cases."""

    @pytest.fixture
    def builder(self):
        return OssSseEventBuilder(run_id="robust-test")

    def test_malformed_upstream_dict(self, builder):
        """Completely malformed upstream should return None safely."""
        # Test various malformed inputs
        malformed_inputs = [
            {},  # Empty dict
            None,  # None input
            "string",  # String instead of dict
            123,  # Number instead of dict
            [],  # List instead of dict
        ]

        for input_val in malformed_inputs:
            result = map_zeroclaw_event_to_oss_event(builder, input_val)
            assert result is None, f"Should return None for {type(input_val).__name__}"

    def test_exception_in_builder_handled(self, builder):
        """Exceptions during event creation should return None safely."""

        # Create a data structure that causes issues when passed to builder
        class BadData:
            def __str__(self):
                raise RuntimeError("Cannot convert to string")

        upstream = {
            "type": "message",
            "data": {
                "role": "assistant",
                "content": BadData(),  # This will cause issues
            },
        }

        # Should not raise, should return None or handle gracefully
        try:
            result = map_zeroclaw_event_to_oss_event(builder, upstream)
            # Either returns None or creates event (implementation dependent)
            # The key point is it doesn't raise
            assert True
        except Exception as e:
            pytest.fail(f"Should not raise exception: {e}")

    def test_unicode_content_handling(self, builder):
        """Unicode content should be handled correctly."""
        upstream = {
            "type": "message",
            "data": {"content": "Hello 世界 🌍 مرحبا", "role": "assistant"},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert event.data["content"] == "Hello 世界 🌍 مرحبا"

    def test_large_arguments_handling(self, builder):
        """Large arguments should be handled without issues."""
        large_args = {"data": "x" * 10000}
        upstream = {
            "type": "tool.call",
            "data": {"tool_id": "tool-1", "name": "process", "arguments": large_args},
        }
        event = map_zeroclaw_event_to_oss_event(builder, upstream)

        assert event is not None
        assert len(event.data["arguments"]["data"]) == 10000
