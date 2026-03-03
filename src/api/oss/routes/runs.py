"""OSS /runs endpoint for end-user execution with SSE streaming.

Provides POST /runs as a typed SSE stream supporting:
- Per-user request ordering via OssUserQueue
- Idempotency via X-Idempotency-Key header
- Session continuity via X-Session-ID header
- Provisioning events for cold start
- One auto-retry for transient failures
"""

import asyncio
from typing import AsyncIterable, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository
from src.api.dependencies.external_identity import (
    resolve_external_principal,
    ExternalPrincipal,
)
from src.services.oss_user_queue import get_oss_user_queue, OssQueueResult
from src.services.oss_sse_events import (
    OssSseEventBuilder,
    OssEventType,
    sanitize_error_for_user,
)
from src.services.run_service import RunService
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope
from src.services.picoclaw_bridge_service import (
    BridgeErrorType,
)


router = APIRouter()


class OssRunError(Exception):
    """Error during OSS run execution."""

    def __init__(
        self, message: str, category: str = "agent_error", retryable: bool = False
    ):
        self.message = message
        self.category = category
        self.retryable = retryable
        super().__init__(message)


async def _execute_run_with_events(
    principal: ExternalPrincipal,
    db: Session,
    input_message: str,
    session_id: Optional[str],
    idempotency_key: Optional[str],
    run_id: str,
) -> AsyncIterable[str]:
    """Execute a run and yield SSE events.

    This generator yields SSE-formatted events throughout the run lifecycle:
    1. queued - Request is queued
    2. provisioning - Workspace/sandbox provisioning (if needed)
    3. running - Execution started
    4. message - Agent message content
    5. completed/failed - Terminal state

    Args:
        principal: External principal from X-User-ID
        db: Database session
        input_message: The user's input message
        session_id: Optional session ID for continuity
        idempotency_key: Optional idempotency key
        run_id: Run identifier for this execution

    Yields:
        SSE-formatted event strings
    """
    event_builder = OssSseEventBuilder(run_id)

    # Track cold start state - will be set inside the user queue lock
    cold_start_detected = False

    try:
        # Yield queued event
        yield event_builder.queued(position=1).to_sse_lines()

        # Get run service and user queue
        run_service = RunService()
        user_queue = get_oss_user_queue()

        # Define the actual execution operation
        # CRITICAL: Cold start check is done INSIDE execute_operation to ensure
        # it's protected by the per-user queue lock. This prevents race conditions
        # where multiple concurrent requests all see empty sandbox list and
        # trigger multiple provisioning events / sandboxes.
        async def execute_operation():
            nonlocal cold_start_detected

            # Check for cold start (no existing sandboxes) - INSIDE the lock
            # This ensures only one request per user can see the cold start state
            sandbox_repo = SandboxInstanceRepository(db)
            workspace_sandboxes = sandbox_repo.list_by_workspace(
                workspace_id=__import__("uuid").UUID(principal.workspace_id)
            )

            if not workspace_sandboxes:
                cold_start_detected = True

            # Route through RunService
            return await run_service.execute_with_routing(
                principal=principal,
                session=db,
                egress_policy=EgressPolicy.allow_all(),
                tool_policy=ToolPolicy.allow_all(),
                secret_policy=SecretScope.allow_all(),
                secrets={},
                input_message=input_message,
                session_id=session_id,
            )

        # Execute with per-user serialization and idempotency
        queue_result: OssQueueResult = await user_queue.execute(
            user_id=principal.external_user_id,
            idempotency_key=idempotency_key,
            operation=execute_operation,
        )

        # Emit provisioning event AFTER user queue lock is acquired and released
        # This ensures only the first request for a cold workspace emits this event
        if cold_start_detected:
            yield event_builder.provisioning(
                step="workspace_ready", message="Workspace ready"
            ).to_sse_lines()

        if queue_result.was_cached:
            # Result was from cache - emit cached indicator
            yield event_builder.running(step="cached_result").to_sse_lines()

        if not queue_result.success:
            # Execution failed
            error_info = sanitize_error_for_user(
                queue_result.error or "Unknown error", category="agent_error"
            )
            yield event_builder.failed(
                error=error_info["message"], error_category=error_info["category"]
            ).to_sse_lines()
            return

        result = queue_result.result

        # Emit running event
        yield event_builder.running(step="bridge_execute").to_sse_lines()

        # Check if the run actually succeeded (not just queue-level success)
        if result and hasattr(result, "status") and result.status == "error":
            # Run execution failed - report failure
            error_msg = result.error or "Run execution failed"
            error_info = sanitize_error_for_user(error_msg, category="agent_error")
            yield event_builder.failed(
                error=error_info["message"], error_category=error_info["category"]
            ).to_sse_lines()
            return

        # Check for bridge output
        if result and hasattr(result, "outputs") and result.outputs:
            outputs = result.outputs

            # Check for final output from bridge
            final_output = outputs.get("final_output")
            if final_output:
                yield event_builder.message(
                    role="assistant", content=str(final_output)
                ).to_sse_lines()
            elif outputs.get("bridge", {}).get("success"):
                bridge_output = outputs["bridge"].get("output", {})
                message = bridge_output.get("message") or bridge_output.get("content")
                if message:
                    yield event_builder.message(
                        role="assistant", content=str(message)
                    ).to_sse_lines()

        # Yield completed event
        yield event_builder.completed().to_sse_lines()

    except Exception as e:
        # Handle unexpected errors
        error_info = sanitize_error_for_user(str(e), category="agent_error")
        yield event_builder.failed(
            error=error_info["message"], error_category=error_info["category"]
        ).to_sse_lines()


from pydantic import BaseModel


class RunRequest(BaseModel):
    """OSS run request body."""

    message: str


@router.post("/runs")
async def runs(
    request: RunRequest,
    principal: ExternalPrincipal = Depends(resolve_external_principal),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """Execute a run and stream results as SSE.

        This endpoint accepts a message from the end-user and streams back
    typed SSE events including:
        - Lifecycle events: queued, provisioning, running, completed/failed
        - Domain events: message (agent responses)

        Headers:
            X-User-ID: Required. Opaque user identifier from gateway.
            X-Session-ID: Optional. Session ID for conversation continuity.
            X-Idempotency-Key: Optional. Key for idempotent request handling.

        Args:
            request: The run request body (contains message)
            principal: External principal resolved from X-User-ID
            x_session_id: Optional session ID for continuity
            x_idempotency_key: Optional idempotency key
            db: Database session

        Returns:
            EventSourceResponse with SSE stream
    """
    run_id = str(uuid4())

    # For now, return a simple streaming response
    # EventSourceResponse requires an async iterable
    async def event_stream():
        async for event in _execute_run_with_events(
            principal=principal,
            db=db,
            input_message=request.message,
            session_id=x_session_id,
            idempotency_key=x_idempotency_key,
            run_id=run_id,
        ):
            yield event

    # Use StreamingResponse for SSE
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Run-ID": run_id,
        },
    )
