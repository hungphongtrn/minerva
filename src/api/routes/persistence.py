"""Persistence query endpoints.

Provides endpoints for querying run/session metadata, runtime event timelines,
checkpoint manifests, active checkpoint pointers, and workspace audit trails.
All endpoints are read-only and support both authenticated and guest access
(with appropriate visibility restrictions).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies.auth import (
    resolve_principal_or_guest,
    AnyPrincipal,
    require_scopes,
)
from src.db.session import get_db
from src.db.repositories import (
    RunSessionRepository,
    RuntimeEventRepository,
    WorkspaceCheckpointRepository,
    AuditEventRepository,
)
from src.db.models import (
    RunSessionState,
    RuntimeEventType,
    CheckpointState,
    AuditEventCategory,
)
from src.services.workspace_checkpoint_service import (
    WorkspaceCheckpointService,
    PointerUpdateForbiddenError,
    PointerRollbackForbiddenError,
)


router = APIRouter(prefix="/persistence", tags=["Persistence"])


# =============================================================================
# Response Models
# =============================================================================


class RunSessionSummary(BaseModel):
    """Summary of a run session."""

    id: str = Field(..., description="Session database ID")
    run_id: str = Field(..., description="Unique run identifier")
    state: str = Field(..., description="Run session state")
    workspace_id: str = Field(..., description="Workspace ID")
    principal_id: Optional[str] = Field(None, description="Principal ID who ran")
    principal_type: Optional[str] = Field(
        None, description="Principal type (user/guest)"
    )
    parent_run_id: Optional[str] = Field(None, description="Parent run ID if nested")
    sandbox_id: Optional[str] = Field(None, description="Associated sandbox ID")
    checkpoint_id: Optional[str] = Field(None, description="Restored checkpoint ID")
    started_at: Optional[str] = Field(None, description="When run started")
    completed_at: Optional[str] = Field(None, description="When run completed")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    created_at: str = Field(..., description="When session was created")


class RuntimeEventSummary(BaseModel):
    """Summary of a runtime event."""

    id: str = Field(..., description="Event database ID")
    run_session_id: str = Field(..., description="Associated run session ID")
    event_type: str = Field(..., description="Type of event")
    occurred_at: str = Field(..., description="When event occurred")
    actor_id: Optional[str] = Field(None, description="Actor who triggered event")
    actor_type: Optional[str] = Field(None, description="Actor type")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    payload: Optional[dict] = Field(None, description="Event payload")


class RunTimelineResponse(BaseModel):
    """Response containing run timeline (session + events)."""

    run_id: str = Field(..., description="Run identifier")
    session: RunSessionSummary = Field(..., description="Run session metadata")
    events: List[RuntimeEventSummary] = Field(..., description="Chronological events")
    event_count: int = Field(..., description="Total number of events")


class CheckpointManifestInfo(BaseModel):
    """Checkpoint manifest details."""

    format_version: str = Field(..., description="Checkpoint format version")
    checkpoint_id: str = Field(..., description="Checkpoint identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    agent_pack_id: str = Field(..., description="Agent pack ID")
    created_at: str = Field(..., description="Creation timestamp")
    file_count: int = Field(..., description="Number of files in checkpoint")
    files: List[dict] = Field(default_factory=list, description="File entries")


class CheckpointSummary(BaseModel):
    """Summary of a checkpoint."""

    id: str = Field(..., description="Database ID")
    checkpoint_id: str = Field(..., description="Checkpoint identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    version: str = Field(..., description="Checkpoint format version")
    state: str = Field(..., description="Checkpoint state")
    storage_key: str = Field(..., description="Storage location key")
    storage_size_bytes: Optional[int] = Field(None, description="Archive size")
    manifest: Optional[CheckpointManifestInfo] = Field(
        None, description="Manifest info"
    )
    created_by_run_id: Optional[str] = Field(None, description="Run that created it")
    previous_checkpoint_id: Optional[str] = Field(None, description="Previous in chain")
    started_at: Optional[str] = Field(None, description="When creation started")
    completed_at: Optional[str] = Field(None, description="When creation completed")
    expires_at: Optional[str] = Field(None, description="Expiration time")
    created_at: str = Field(..., description="Record creation time")


class ActiveCheckpointResponse(BaseModel):
    """Response containing active checkpoint pointer."""

    workspace_id: str = Field(..., description="Workspace ID")
    active_checkpoint_id: Optional[str] = Field(
        None, description="Active checkpoint ID"
    )
    checkpoint_db_id: Optional[str] = Field(None, description="Active checkpoint DB ID")
    changed_by: Optional[str] = Field(None, description="Who last changed pointer")
    changed_reason: Optional[str] = Field(None, description="Reason for change")
    updated_at: Optional[str] = Field(None, description="When pointer was last updated")
    checkpoint: Optional[CheckpointSummary] = Field(
        None, description="Checkpoint details"
    )


class CheckpointListResponse(BaseModel):
    """Response containing list of checkpoints."""

    workspace_id: str = Field(..., description="Workspace ID")
    checkpoints: List[CheckpointSummary] = Field(..., description="Checkpoint list")
    count: int = Field(..., description="Total count")


class AuditEventSummary(BaseModel):
    """Summary of an audit event."""

    id: str = Field(..., description="Event database ID")
    category: str = Field(..., description="Event category")
    action: str = Field(..., description="Action performed")
    outcome: str = Field(..., description="Outcome (success/failure/denied)")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: str = Field(..., description="Resource identifier")
    actor_id: Optional[str] = Field(None, description="Actor who performed action")
    actor_type: Optional[str] = Field(None, description="Actor type")
    occurred_at: str = Field(..., description="When event occurred")
    reason: Optional[str] = Field(None, description="Reason or additional context")
    immutable: bool = Field(..., description="Whether event is immutable")


class AuditTimelineResponse(BaseModel):
    """Response containing workspace audit timeline."""

    workspace_id: str = Field(..., description="Workspace ID")
    events: List[AuditEventSummary] = Field(..., description="Audit events")
    count: int = Field(..., description="Total count")
    category_filter: Optional[str] = Field(None, description="Applied category filter")


class PointerUpdateRequest(BaseModel):
    """Request to update active checkpoint pointer."""

    checkpoint_id: str = Field(..., description="Checkpoint ID to set as active")
    reason: Optional[str] = Field(None, description="Reason for pointer change")


class PointerUpdateResponse(BaseModel):
    """Response from pointer update."""

    workspace_id: str = Field(..., description="Workspace ID")
    active_checkpoint_id: str = Field(..., description="New active checkpoint ID")
    changed_by: Optional[str] = Field(None, description="Who changed the pointer")
    changed_reason: Optional[str] = Field(None, description="Reason for change")
    updated_at: str = Field(..., description="When pointer was updated")


class ErrorResponse(BaseModel):
    """Error response."""

    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type code")
    remediation: Optional[str] = Field(None, description="Remediation guidance")


# =============================================================================
# Helper Functions
# =============================================================================


def _serialize_run_session(session: Any) -> dict:
    """Serialize a RunSession to dict."""
    # Handle enum (PostgreSQL) vs string (SQLite)
    state = session.state
    if hasattr(state, "value"):
        state = state.value

    return {
        "id": str(session.id),
        "run_id": session.run_id,
        "state": state,
        "workspace_id": str(session.workspace_id),
        "principal_id": session.principal_id,
        "principal_type": session.principal_type,
        "parent_run_id": session.parent_run_id,
        "sandbox_id": str(session.sandbox_id) if session.sandbox_id else None,
        "checkpoint_id": str(session.checkpoint_id) if session.checkpoint_id else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat()
        if session.completed_at
        else None,
        "duration_ms": session.duration_ms,
        "error_code": session.error_code,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


def _serialize_runtime_event(event: Any) -> dict:
    """Serialize a RuntimeEvent to dict."""
    # Handle enum (PostgreSQL) vs string (SQLite)
    event_type = event.event_type
    if hasattr(event_type, "value"):
        event_type = event_type.value

    # Parse payload JSON if present
    payload = None
    if event.payload_json:
        try:
            import json

            payload = json.loads(event.payload_json)
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": event.payload_json}

    return {
        "id": str(event.id),
        "run_session_id": str(event.run_session_id),
        "event_type": event_type,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "correlation_id": event.correlation_id,
        "payload": payload,
    }


def _serialize_checkpoint(checkpoint: Any) -> dict:
    """Serialize a WorkspaceCheckpoint to dict."""
    # Handle enum (PostgreSQL) vs string (SQLite)
    state = checkpoint.state
    if hasattr(state, "value"):
        state = state.value

    # Parse manifest if present
    manifest = None
    if checkpoint.manifest_json:
        try:
            import json

            manifest_data = json.loads(checkpoint.manifest_json)
            manifest = {
                "format_version": manifest_data.get("format_version", "unknown"),
                "checkpoint_id": manifest_data.get(
                    "checkpoint_id", checkpoint.checkpoint_id
                ),
                "workspace_id": manifest_data.get(
                    "workspace_id", str(checkpoint.workspace_id)
                ),
                "agent_pack_id": manifest_data.get("agent_pack_id", "unknown"),
                "created_at": manifest_data.get(
                    "created_at",
                    checkpoint.created_at.isoformat()
                    if checkpoint.created_at
                    else None,
                ),
                "file_count": len(manifest_data.get("files", [])),
                "files": manifest_data.get("files", []),
            }
        except (json.JSONDecodeError, ValueError):
            manifest = None

    return {
        "id": str(checkpoint.id),
        "checkpoint_id": checkpoint.checkpoint_id,
        "workspace_id": str(checkpoint.workspace_id),
        "version": checkpoint.version,
        "state": state,
        "storage_key": checkpoint.storage_key,
        "storage_size_bytes": checkpoint.storage_size_bytes,
        "manifest": manifest,
        "created_by_run_id": checkpoint.created_by_run_id,
        "previous_checkpoint_id": str(checkpoint.previous_checkpoint_id)
        if checkpoint.previous_checkpoint_id
        else None,
        "started_at": checkpoint.started_at.isoformat()
        if checkpoint.started_at
        else None,
        "completed_at": checkpoint.completed_at.isoformat()
        if checkpoint.completed_at
        else None,
        "expires_at": checkpoint.expires_at.isoformat()
        if checkpoint.expires_at
        else None,
        "created_at": checkpoint.created_at.isoformat()
        if checkpoint.created_at
        else None,
    }


def _serialize_audit_event(event: Any) -> dict:
    """Serialize an AuditEvent to dict."""
    # Handle enum (PostgreSQL) vs string (SQLite)
    category = event.category
    if hasattr(category, "value"):
        category = category.value

    return {
        "id": str(event.id),
        "category": category,
        "action": event.action,
        "outcome": event.outcome,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "reason": event.reason,
        "immutable": event.immutable,
    }


# =============================================================================
# Endpoints - Run Timeline
# =============================================================================


@router.get(
    "/runs/{run_id}/timeline",
    response_model=RunTimelineResponse,
    summary="Get run timeline",
    description="Get the complete timeline for a run including session metadata and chronological events.",
    responses={
        404: {"description": "Run not found", "model": ErrorResponse},
    },
)
async def get_run_timeline(
    run_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> RunTimelineResponse:
    """Get run timeline with session metadata and ordered events.

    Returns complete run information including session state and all runtime events
    in chronological order.
    """
    run_repo = RunSessionRepository(db)
    event_repo = RuntimeEventRepository(db)

    # Get run session
    session = run_repo.get_by_run_id(run_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Run '{run_id}' not found",
                "error_type": "run_not_found",
                "remediation": "Verify the run_id is correct",
            },
        )

    # Get events in chronological order
    events = event_repo.list_by_run_session_chronological(session.id, limit=1000)

    return RunTimelineResponse(
        run_id=run_id,
        session=RunSessionSummary(**_serialize_run_session(session)),
        events=[RuntimeEventSummary(**_serialize_runtime_event(e)) for e in events],
        event_count=len(events),
    )


@router.get(
    "/runs/{run_id}/events",
    response_model=List[RuntimeEventSummary],
    summary="Get run events",
    description="Get runtime events for a specific run in chronological order.",
)
async def get_run_events(
    run_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> List[RuntimeEventSummary]:
    """Get runtime events for a run."""
    run_repo = RunSessionRepository(db)
    event_repo = RuntimeEventRepository(db)

    # Get run session
    session = run_repo.get_by_run_id(run_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Run '{run_id}' not found",
                "error_type": "run_not_found",
            },
        )

    # Get events
    events = event_repo.list_by_run_session_chronological(session.id, limit=limit)

    return [RuntimeEventSummary(**_serialize_runtime_event(e)) for e in events]


# =============================================================================
# Endpoints - Checkpoint Metadata
# =============================================================================


@router.get(
    "/workspaces/{workspace_id}/checkpoints",
    response_model=CheckpointListResponse,
    summary="List workspace checkpoints",
    description="List all checkpoints for a workspace with optional state filter.",
)
async def list_checkpoints(
    workspace_id: UUID,
    state: Optional[str] = Query(
        None, description="Filter by state (pending/completed/failed)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> CheckpointListResponse:
    """List checkpoints for a workspace."""
    repo = WorkspaceCheckpointRepository(db)

    # Convert string state to constant if provided
    state_filter = None
    if state:
        state_lower = state.lower()
        valid_states = {
            "pending": CheckpointState.PENDING,
            "in_progress": CheckpointState.IN_PROGRESS,
            "completed": CheckpointState.COMPLETED,
            "failed": CheckpointState.FAILED,
            "partial": CheckpointState.PARTIAL,
        }
        if state_lower not in valid_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"Invalid state: {state}",
                    "error_type": "invalid_state",
                    "remediation": "Use one of: pending, in_progress, completed, failed, partial",
                },
            )
        state_filter = valid_states[state_lower]

    checkpoints = repo.list_by_workspace(
        workspace_id=workspace_id,
        state=state_filter,
        limit=limit,
    )

    return CheckpointListResponse(
        workspace_id=str(workspace_id),
        checkpoints=[
            CheckpointSummary(**_serialize_checkpoint(c)) for c in checkpoints
        ],
        count=len(checkpoints),
    )


@router.get(
    "/workspaces/{workspace_id}/checkpoints/{checkpoint_id}",
    response_model=CheckpointSummary,
    summary="Get checkpoint details",
    description="Get detailed information about a specific checkpoint including manifest.",
    responses={
        404: {"description": "Checkpoint not found", "model": ErrorResponse},
    },
)
async def get_checkpoint(
    workspace_id: UUID,
    checkpoint_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> CheckpointSummary:
    """Get checkpoint details by checkpoint_id."""
    repo = WorkspaceCheckpointRepository(db)

    checkpoint = repo.get_by_checkpoint_id_and_workspace(checkpoint_id, workspace_id)
    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Checkpoint '{checkpoint_id}' not found in workspace",
                "error_type": "checkpoint_not_found",
                "remediation": "Verify the checkpoint_id and workspace_id are correct",
            },
        )

    return CheckpointSummary(**_serialize_checkpoint(checkpoint))


@router.get(
    "/workspaces/{workspace_id}/active-checkpoint",
    response_model=ActiveCheckpointResponse,
    summary="Get active checkpoint pointer",
    description="Get the currently active checkpoint for a workspace.",
)
async def get_active_checkpoint(
    workspace_id: UUID,
    include_checkpoint: bool = Query(
        True, description="Include full checkpoint details"
    ),
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> ActiveCheckpointResponse:
    """Get the active checkpoint pointer for a workspace.

    Returns the active checkpoint pointer with optional full checkpoint details.
    """
    service = WorkspaceCheckpointService(db)
    checkpoint_repo = WorkspaceCheckpointRepository(db)

    # Get active checkpoint info
    checkpoint = service.get_active_checkpoint(workspace_id)

    if not checkpoint:
        return ActiveCheckpointResponse(
            workspace_id=str(workspace_id),
            active_checkpoint_id=None,
            checkpoint_db_id=None,
            changed_by=None,
            changed_reason=None,
            updated_at=None,
            checkpoint=None,
        )

    # Get pointer metadata from active_checkpoint record
    pointer_info = checkpoint_repo.get_active_checkpoint(workspace_id)
    active_pointer = checkpoint_repo._session.execute(
        __import__("sqlalchemy")
        .select(
            __import__(
                "src.db.models", fromlist=["WorkspaceActiveCheckpoint"]
            ).WorkspaceActiveCheckpoint
        )
        .where(
            __import__(
                "src.db.models", fromlist=["WorkspaceActiveCheckpoint"]
            ).WorkspaceActiveCheckpoint.workspace_id
            == workspace_id
        )
    ).scalar_one_or_none()

    return ActiveCheckpointResponse(
        workspace_id=str(workspace_id),
        active_checkpoint_id=checkpoint["checkpoint_id"],
        checkpoint_db_id=checkpoint["id"],
        changed_by=active_pointer.changed_by if active_pointer else None,
        changed_reason=active_pointer.changed_reason if active_pointer else None,
        updated_at=active_pointer.updated_at.isoformat()
        if active_pointer and active_pointer.updated_at
        else None,
        checkpoint=CheckpointSummary(**checkpoint) if include_checkpoint else None,
    )


# =============================================================================
# Endpoints - Audit Timeline
# =============================================================================


@router.get(
    "/workspaces/{workspace_id}/audit",
    response_model=AuditTimelineResponse,
    summary="Get workspace audit timeline",
    description="Get audit events for a workspace in reverse chronological order.",
)
async def get_workspace_audit(
    workspace_id: UUID,
    category: Optional[str] = Query(None, description="Filter by category"),
    since: Optional[datetime] = Query(
        None, description="Start time filter (ISO format)"
    ),
    until: Optional[datetime] = Query(None, description="End time filter (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> AuditTimelineResponse:
    """Get audit events for a workspace.

    Returns audit events in reverse chronological order (newest first).
    Supports filtering by category and time range.
    """
    repo = AuditEventRepository(db)

    # Convert string category to constant if provided
    category_filter = None
    if category:
        category_lower = category.lower()
        valid_categories = {
            "run_execution": AuditEventCategory.RUN_EXECUTION,
            "checkpoint_management": AuditEventCategory.CHECKPOINT_MANAGEMENT,
            "policy_enforcement": AuditEventCategory.POLICY_ENFORCEMENT,
            "system_operation": AuditEventCategory.SYSTEM_OPERATION,
        }
        if category_lower not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"Invalid category: {category}",
                    "error_type": "invalid_category",
                    "remediation": "Use one of: run_execution, checkpoint_management, policy_enforcement, system_operation",
                },
            )
        category_filter = valid_categories[category_lower]

    events = repo.list_by_workspace(
        workspace_id=workspace_id,
        category=category_filter,
        since=since,
        until=until,
        limit=limit,
    )

    return AuditTimelineResponse(
        workspace_id=str(workspace_id),
        events=[AuditEventSummary(**_serialize_audit_event(e)) for e in events],
        count=len(events),
        category_filter=category,
    )


@router.get(
    "/audit/events/{event_id}",
    response_model=AuditEventSummary,
    summary="Get audit event details",
    description="Get details of a specific audit event by ID.",
    responses={
        404: {"description": "Audit event not found", "model": ErrorResponse},
    },
)
async def get_audit_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> AuditEventSummary:
    """Get a specific audit event by ID."""
    repo = AuditEventRepository(db)

    event = repo.get_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Audit event '{event_id}' not found",
                "error_type": "audit_event_not_found",
            },
        )

    return AuditEventSummary(**_serialize_audit_event(event))


# =============================================================================
# Endpoints - Workspace Run Sessions
# =============================================================================


@router.get(
    "/workspaces/{workspace_id}/runs",
    response_model=List[RunSessionSummary],
    summary="List workspace runs",
    description="List run sessions for a workspace.",
)
async def list_workspace_runs(
    workspace_id: UUID,
    state: Optional[str] = Query(None, description="Filter by state"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> List[RunSessionSummary]:
    """List run sessions for a workspace."""
    repo = RunSessionRepository(db)

    # Convert string state to constant if provided
    state_filter = None
    if state:
        state_lower = state.lower()
        valid_states = {
            "queued": RunSessionState.QUEUED,
            "running": RunSessionState.RUNNING,
            "paused": RunSessionState.PAUSED,
            "completed": RunSessionState.COMPLETED,
            "failed": RunSessionState.FAILED,
            "cancelled": RunSessionState.CANCELLED,
        }
        if state_lower not in valid_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"Invalid state: {state}",
                    "error_type": "invalid_state",
                    "remediation": "Use one of: queued, running, paused, completed, failed, cancelled",
                },
            )
        state_filter = valid_states[state_lower]

    sessions = repo.list_by_workspace(
        workspace_id=workspace_id,
        state=state_filter,
        limit=limit,
    )

    return [RunSessionSummary(**_serialize_run_session(s)) for s in sessions]


# =============================================================================
# Endpoints - Checkpoint Pointer Management
# =============================================================================


@router.post(
    "/workspaces/{workspace_id}/active-checkpoint",
    response_model=PointerUpdateResponse,
    summary="Update active checkpoint pointer",
    description="Set the active checkpoint for a workspace. Operator-only in Phase 3.",
    responses={
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Checkpoint not found", "model": ErrorResponse},
        400: {"description": "Invalid pointer transition", "model": ErrorResponse},
    },
)
async def update_active_checkpoint(
    workspace_id: UUID,
    request: PointerUpdateRequest,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> PointerUpdateResponse:
    """Update the active checkpoint pointer.

    Phase 3 restrictions:
    - Only operators can change the pointer
    - Cannot rollback to older revisions (must advance to newest)
    - All changes are audited

    Returns the updated pointer information.
    """
    # Use service to set active checkpoint with guardrails
    service = WorkspaceCheckpointService(db)

    # Get checkpoint to find its DB ID
    checkpoint_repo = WorkspaceCheckpointRepository(db)
    checkpoint = checkpoint_repo.get_by_checkpoint_id_and_workspace(
        request.checkpoint_id, workspace_id
    )

    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Checkpoint '{request.checkpoint_id}' not found in workspace",
                "error_type": "checkpoint_not_found",
                "remediation": "Verify the checkpoint_id is correct and belongs to this workspace",
            },
        )

    # Get principal ID for audit
    principal_id = getattr(
        principal, "principal_id", str(getattr(principal, "workspace_id", "unknown"))
    )

    # Determine if principal is an operator (has write scope or admin scope)
    principal_scopes = getattr(principal, "scopes", [])
    is_operator = (
        "admin" in principal_scopes
        or "*" in principal_scopes
        or "workspace:write" in principal_scopes
    )

    try:
        result = service.set_active_checkpoint_guarded(
            workspace_id=workspace_id,
            checkpoint_db_id=checkpoint.id,
            changed_by=principal_id,
            changed_reason=request.reason or "Manual pointer update via API",
            is_operator=is_operator,
        )
    except PointerUpdateForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": str(e),
                "error_type": "pointer_update_forbidden",
                "remediation": "Contact an operator to change the active checkpoint pointer",
            },
        )
    except PointerRollbackForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": str(e),
                "error_type": "pointer_rollback_forbidden",
                "remediation": "In Phase 3, you can only advance to the newest checkpoint. Rollback to older revisions is not allowed.",
            },
        )

    return PointerUpdateResponse(
        workspace_id=result["workspace_id"],
        active_checkpoint_id=checkpoint.checkpoint_id,
        changed_by=result["changed_by"],
        changed_reason=result["changed_reason"],
        updated_at=result["updated_at"],
    )
