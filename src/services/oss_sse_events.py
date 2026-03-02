"""Typed SSE event helper for OSS streaming.

Provides:
- Typed SSE event envelope with stable fields
- Lifecycle events: queued, running, completed, failed
- Domain events: message, tool_call, tool_result, ui_patch, state_update, error
- Error sanitization for end-user consumption
"""

import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Optional, Union


class OssEventType(str, Enum):
    """Event types for OSS SSE streaming."""
    # Lifecycle events
    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    # Domain events
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    UI_PATCH = "ui_patch"
    STATE_UPDATE = "state_update"
    ERROR = "error"


@dataclass
class OssSseEvent:
    """Typed SSE event envelope for OSS streaming.

    Envelope fields (stable):
    - id: Event sequence ID for replay/ordering
    - type: Event type from OssEventType
    - ts: Unix timestamp (seconds since epoch)
    - run_id: Run identifier for correlation
    - data: Event-specific payload

    The envelope format is designed to be:
    - Stable across API versions
    - Extensible via data field
    - Compatible with SSE protocol
    """
    id: str
    type: str  # OssEventType value
    ts: float
    run_id: str
    data: Dict[str, Any]

    def to_sse_dict(self) -> Dict[str, Any]:
        """Convert to dict for EventSourceResponse.

        Returns:
            Dict with event envelope fields
        """
        return {
            "id": self.id,
            "event": self.type,
            "data": json.dumps({
                "ts": self.ts,
                "run_id": self.run_id,
                "data": self.data,
            }),
        }

    def to_sse_lines(self) -> str:
        """Convert to SSE format lines.

        Returns:
            SSE formatted string (id:, event:, data: lines)
        """
        # Handle both enum and string types
        event_type = self.type.value if hasattr(self.type, 'value') else self.type
        lines = [
            f"id: {self.id}",
            f"event: {event_type}",
            f"data: {json.dumps({
                'ts': self.ts,
                'run_id': self.run_id,
                'data': self.data,
            })}",
            "",  # Empty line terminates event
            "",  # Extra empty line for SSE protocol
        ]
        return "\n".join(lines)


class OssSseEventBuilder:
    """Builder for creating typed SSE events.

    Provides factory methods for all standard event types with
    proper error sanitization for end-user consumption.
    """

    def __init__(self, run_id: str):
        """Initialize the event builder.

        Args:
            run_id: Run identifier for all events
        """
        self._run_id = run_id
        self._sequence = 0

    def _next_id(self) -> str:
        """Generate next sequence ID."""
        self._sequence += 1
        return f"{self._run_id}:{self._sequence}"

    def _now(self) -> float:
        """Get current timestamp."""
        return time.time()

    def queued(self, position: int = 1, **extra) -> OssSseEvent:
        """Create queued event.

        Args:
            position: Queue position (1 = next to run)
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"position": position, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.QUEUED,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def provisioning(self, step: str, message: Optional[str] = None, **extra) -> OssSseEvent:
        """Create provisioning status event.

        Args:
            step: Provisioning step label (e.g., "workspace_create", "sandbox_create")
            message: Human-readable status message
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"step": step, **extra}
        if message:
            data["message"] = message
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.PROVISIONING,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def running(self, step: Optional[str] = None, **extra) -> OssSseEvent:
        """Create running event.

        Args:
            step: Optional execution step label
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = extra
        if step:
            data["step"] = step
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.RUNNING,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def completed(self, **extra) -> OssSseEvent:
        """Create completed event.

        Args:
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.COMPLETED,
            ts=self._now(),
            run_id=self._run_id,
            data=extra,
        )

    def failed(self, error: str, error_category: Optional[str] = None, **extra) -> OssSseEvent:
        """Create failed event.

        Args:
            error: Human-readable error message (sanitized)
            error_category: Optional error category for client handling
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"error": error, **extra}
        if error_category:
            data["category"] = error_category
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.FAILED,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def message(self, role: str, content: str, **extra) -> OssSseEvent:
        """Create message event.

        Args:
            role: Message role (e.g., "assistant", "user")
            content: Message content
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"role": role, "content": content, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.MESSAGE,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def tool_call(self, tool_id: str, name: str, arguments: Dict[str, Any], **extra) -> OssSseEvent:
        """Create tool_call event.

        Args:
            tool_id: Tool invocation ID
            name: Tool name
            arguments: Tool arguments
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"tool_id": tool_id, "name": name, "arguments": arguments, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.TOOL_CALL,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def tool_result(self, tool_id: str, result: Any, **extra) -> OssSseEvent:
        """Create tool_result event.

        Args:
            tool_id: Tool invocation ID
            result: Tool execution result
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"tool_id": tool_id, "result": result, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.TOOL_RESULT,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def ui_patch(self, patch: Dict[str, Any], **extra) -> OssSseEvent:
        """Create ui_patch event.

        Args:
            patch: UI patch data (format depends on frontend contract)
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"patch": patch, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.UI_PATCH,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def state_update(self, state: Dict[str, Any], **extra) -> OssSseEvent:
        """Create state_update event.

        Args:
            state: State update data
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {"state": state, **extra}
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.STATE_UPDATE,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )

    def error(
        self,
        message: str,
        category: str = "agent_error",
        retryable: bool = False,
        **extra
    ) -> OssSseEvent:
        """Create error event (non-terminal).

        Args:
            message: Human-readable error message (sanitized)
            category: Error category (provisioning_failed, agent_error, rate_limited)
            retryable: Whether client can retry
            **extra: Additional data fields

        Returns:
            OssSseEvent
        """
        data = {
            "message": message,
            "category": category,
            "retryable": retryable,
            **extra,
        }
        return OssSseEvent(
            id=self._next_id(),
            type=OssEventType.ERROR,
            ts=self._now(),
            run_id=self._run_id,
            data=data,
        )


def sanitize_error_for_user(error: Union[str, Exception, Dict[str, Any]], category: str = "agent_error") -> Dict[str, str]:
    """Sanitize internal error for end-user consumption.

    Removes sensitive information like:
    - Tokens, API keys
    - Internal sandbox URLs
    - Stack traces
    - Database IDs
    - Internal service names

    Args:
        error: The internal error (string, exception, or dict)
        category: Error category for client handling

    Returns:
        Sanitized error dict with message and category
    """
    # Extract error message
    if isinstance(error, dict):
        message = error.get("message", str(error))
    elif isinstance(error, Exception):
        message = str(error)
    else:
        message = str(error)

    # List of patterns to sanitize (replace with generic message)
    # Order matters: more specific patterns first
    sensitive_patterns = [
        # Internal IDs (UUIDs) - must come before generic token regex
        (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "[ID]"),

        # URLs with credentials
        (r"https?://[^:]+:[^@]+@", "https://[REDACTED]@"),

        # Bearer tokens (specific pattern)
        (r"bearer\s+\S+", "bearer [REDACTED]"),

        # API keys (specific pattern)
        (r"api[_-]?key[=:]\S+", "api_key=[REDACTED]"),

        # Generic token patterns (handle values with hyphens, underscores, etc.)
        (r"token[:=][\w\-]+", "token=[REDACTED]"),

        # Stack trace indicators
        (r"File \"[^\"]+\", line \d+", "[LOCATION]"),
        (r"Traceback \(most recent call last\)", "[TRACE]"),
    ]

    import re
    sanitized = message
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # Map internal error categories to user-facing ones
    category_map = {
        "provisioning_failed": "provisioning_failed",
        "sandbox_provision_failed": "provisioning_failed",
        "provider_unavailable": "provisioning_failed",
        "bridge_auth_failed": "agent_error",
        "bridge_timeout": "agent_error",
        "bridge_transport_error": "agent_error",
        "bridge_upstream_error": "agent_error",
        "rate_limited": "rate_limited",
        "lease_conflict": "rate_limited",
    }

    user_category = category_map.get(category, category)

    return {
        "message": sanitized,
        "category": user_category,
    }
