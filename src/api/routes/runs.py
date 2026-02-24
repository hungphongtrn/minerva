"""Run execution endpoints.

Provides endpoints for starting and executing runs with
full runtime policy enforcement and guest mode support.
"""

from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies.auth import resolve_principal_or_guest, AnyPrincipal
from src.db.session import get_db
from src.guest.identity import is_guest_principal
from src.services.run_service import RunService, RunContext, RunResult
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope
from sqlalchemy.orm import Session


router = APIRouter(prefix="/runs", tags=["Runs"])


# Request/Response Models


class StartRunRequest(BaseModel):
    """Request to start a new run."""

    agent_pack_id: Optional[str] = Field(
        None, description="Optional agent pack to execute"
    )
    input: Dict[str, Any] = Field(
        default_factory=dict, description="Input parameters for the run"
    )

    # Runtime intents (what the run will attempt to do)
    requested_egress_urls: list[str] = Field(
        default_factory=list,
        description="Egress URLs the run will access (must be allowed by allowed_hosts)",
    )
    requested_tools: list[str] = Field(
        default_factory=list,
        description="Tools the run will invoke (must be allowed by allowed_tools)",
    )

    # Policy configuration
    allowed_hosts: list[str] = Field(
        default_factory=list, description="Allowed egress hosts (default: none)"
    )
    allowed_tools: list[str] = Field(
        default_factory=list, description="Allowed tools (default: none)"
    )
    allowed_secrets: list[str] = Field(
        default_factory=list, description="Allowed secrets to inject (default: none)"
    )

    # Secrets for this run
    secrets: Dict[str, str] = Field(
        default_factory=dict,
        description="Secrets to make available (filtered by allowed_secrets)",
    )


class StartRunResponse(BaseModel):
    """Response when starting a run."""

    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Run status")
    is_guest: bool = Field(..., description="Whether running in guest mode")
    message: str = Field(..., description="Status message")
    injected_secrets: list[str] = Field(
        default_factory=list, description="Secrets that were injected (based on policy)"
    )


class RunErrorResponse(BaseModel):
    """Response for run errors."""

    run_id: str = Field(..., description="Run identifier")
    status: str = Field(default="error")
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error")
    action: Optional[str] = Field(
        None, description="Action that was denied (egress, tool, secret)"
    )
    resource: Optional[str] = Field(
        None, description="Resource that was denied access to"
    )
    reason: Optional[str] = Field(None, description="Reason for denial")


# Endpoints


@router.post(
    "",
    response_model=StartRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new run",
    description="Start a new run with workspace lifecycle routing and runtime policy enforcement. Resolves healthy sandbox or provisions replacement.",
    responses={
        403: {"description": "Policy violation", "model": RunErrorResponse},
        409: {"description": "Workspace lease conflict"},
        503: {"description": "Sandbox unavailable"},
    },
)
async def start_run(
    request: StartRunRequest,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> StartRunResponse:
    """Start a new run with routing and policy enforcement.

    This endpoint:
    1. Resolves workspace and acquires write lease
    2. Routes to healthy active sandbox or provisions replacement
    3. Enforces runtime policies (egress, tools, secrets)
    4. Executes the run

    Accepts both authenticated and guest requests.
    Guest requests run in non-persistent mode without workspace binding.
    """
    # Initialize service
    service = RunService()

    # Create policies from request
    egress_policy = EgressPolicy(allowed_hosts=request.allowed_hosts)
    tool_policy = ToolPolicy(allowed_tools=request.allowed_tools)
    secret_policy = SecretScope(allowed_secrets=request.allowed_secrets)

    # Extract runtime intents from request
    requested_egress_urls = request.requested_egress_urls.copy()
    if not requested_egress_urls and request.input.get("url"):
        requested_egress_urls.append(request.input["url"])

    requested_tools = request.requested_tools.copy()
    if not requested_tools and request.input.get("tool"):
        requested_tools.append(request.input["tool"])

    # Execute with full routing and policy enforcement
    result = await service.execute_with_routing(
        principal=principal,
        session=db,
        egress_policy=egress_policy,
        tool_policy=tool_policy,
        secret_policy=secret_policy,
        secrets=request.secrets,
        requested_egress_urls=requested_egress_urls,
        requested_tools=requested_tools,
        agent_pack_id=request.agent_pack_id,
    )

    # Handle errors
    if result.status == "error":
        # Check for lease conflict
        if result.error and (
            "lease" in result.error.lower() or "conflict" in result.error.lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": result.error,
                    "error_type": "lease_conflict",
                    "action": "Retry after current operation completes",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result.error
        )

    if result.status == "denied":
        # Parse policy violation error for structured response
        detail = {"error": result.error, "status": "denied"}
        if result.error and "Policy violation" in result.error:
            try:
                import re

                match = re.match(
                    r"Policy violation \(([^)]+)\): (.+?) - (.+)", result.error
                )
                if match:
                    detail["action"] = match.group(1)
                    detail["resource"] = match.group(2)
                    detail["reason"] = match.group(3)
            except Exception:
                pass

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    # Check for routing issues (sandbox unavailable)
    routing_info = result.outputs.get("routing", {}) if result.outputs else {}
    if not routing_info.get("sandbox_id") and not is_guest_principal(principal):
        # Non-guest run without sandbox
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "No healthy sandbox available",
                "workspace_id": routing_info.get("workspace_id"),
                "action": "Retry request or contact support",
            },
        )

    # Build response
    is_guest = is_guest_principal(principal)
    message = (
        "Run executed in guest mode (non-persistent)"
        if is_guest
        else f"Run executed with sandbox {routing_info.get('sandbox_state', 'unknown')}"
    )

    return StartRunResponse(
        run_id=result.run_id,
        status=result.status,
        is_guest=is_guest,
        message=message,
        injected_secrets=result.outputs.get("secrets_injected", [])
        if result.outputs
        else [],
    )


@router.get(
    "/{run_id}",
    summary="Get run status",
    description="Get the status of a run by ID.",
)
async def get_run(
    run_id: str,
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> Dict[str, Any]:
    """Get run status.

    Note: Guest runs are ephemeral and won't be retrievable after execution.
    """
    # For now, return a placeholder
    # Real implementation would look up run in database
    is_guest = is_guest_principal(principal)

    if is_guest:
        return {
            "run_id": run_id,
            "status": "unknown",
            "message": "Guest runs are ephemeral and not persisted",
        }

    # Placeholder for authenticated runs
    return {
        "run_id": run_id,
        "status": "not_implemented",
        "message": "Run retrieval not yet implemented",
    }
