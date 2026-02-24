"""Agent pack management endpoints.

Provides endpoints for scaffolding, registering, and validating
agent packs with path-linked registration and stale detection.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies.auth import resolve_principal_or_guest, AnyPrincipal
from src.db.session import get_db
from src.services.agent_pack_service import AgentPackService
from src.services.agent_scaffold_service import AgentScaffoldService
from src.guest.identity import is_guest_principal


router = APIRouter(prefix="/agent-packs", tags=["Agent Packs"])


# Request/Response Models


class ScaffoldRequest(BaseModel):
    """Request to scaffold agent pack files."""

    pack_path: str = Field(
        ...,
        description="Path to the pack directory (relative or absolute)",
        examples=["./my-agent-pack", "/home/user/agents/my-pack"],
    )
    overwrite: bool = Field(
        default=False,
        description="If True, overwrite existing files with templates",
    )


class ScaffoldEntry(BaseModel):
    """Single scaffold entry result."""

    path: str = Field(..., description="Path to the entry")
    entry_type: str = Field(..., description="Type: file or directory")
    created: bool = Field(..., description="True if created, False if already existed")
    already_existed: bool = Field(..., description="True if entry already existed")


class ScaffoldResponse(BaseModel):
    """Response when scaffolding agent pack."""

    success: bool = Field(..., description="Whether scaffolding succeeded")
    pack_path: str = Field(..., description="Resolved absolute path")
    entries: List[ScaffoldEntry] = Field(
        ..., description="List of created/verified entries"
    )
    message: str = Field(..., description="Status message")


class RegisterRequest(BaseModel):
    """Request to register an agent pack."""

    name: str = Field(
        ...,
        description="Human-readable name for the pack",
        min_length=1,
        max_length=255,
    )
    source_path: str = Field(
        ...,
        description="Filesystem path to the pack folder",
        examples=["./my-agent-pack", "/home/user/agents/my-pack"],
    )


class ChecklistEntry(BaseModel):
    """Single validation checklist entry."""

    code: str = Field(..., description="Machine-readable code (e.g., 'missing_file')")
    path: str = Field(..., description="Path within the pack")
    message: str = Field(..., description="Human-readable description")
    severity: str = Field(..., description="ERROR, WARNING, or INFO")


class ValidationReport(BaseModel):
    """Validation report for an agent pack."""

    is_valid: bool = Field(..., description="True if pack passed validation")
    checklist: List[ChecklistEntry] = Field(..., description="All validation entries")
    source_digest: Optional[str] = Field(
        None, description="SHA-256 digest of pack content"
    )
    error_count: int = Field(..., description="Number of error entries")
    warning_count: int = Field(..., description="Number of warning entries")


class RegisterResponse(BaseModel):
    """Response when registering an agent pack."""

    success: bool = Field(..., description="Whether registration succeeded")
    pack_id: Optional[str] = Field(None, description="Pack ID if registered")
    pack_name: Optional[str] = Field(None, description="Pack name")
    validation: ValidationReport = Field(..., description="Validation report")
    errors: List[str] = Field(default_factory=list, description="Error messages")


class RevalidateResponse(BaseModel):
    """Response when revalidating an agent pack."""

    success: bool = Field(..., description="Whether revalidation succeeded")
    pack_id: str = Field(..., description="Pack ID")
    validation: ValidationReport = Field(..., description="Updated validation report")
    errors: List[str] = Field(default_factory=list, description="Error messages")


class StaleCheckResponse(BaseModel):
    """Response when checking if pack is stale."""

    is_stale: bool = Field(..., description="True if source has changed")
    current_digest: Optional[str] = Field(None, description="Current computed digest")
    stored_digest: Optional[str] = Field(None, description="Previously stored digest")
    pack_id: str = Field(..., description="Pack ID")


class PackStatusResponse(BaseModel):
    """Response for pack status."""

    pack_id: str = Field(..., description="Pack identifier")
    name: str = Field(..., description="Pack name")
    source_path: str = Field(..., description="Filesystem path")
    validation_status: str = Field(..., description="pending/valid/invalid/stale")
    is_active: bool = Field(..., description="Whether pack is active")
    last_validated_at: Optional[str] = Field(
        None, description="Last validation timestamp"
    )


# Endpoints


@router.post(
    "/scaffold",
    response_model=ScaffoldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Scaffold agent pack",
    description="Create required Picoclaw template files (AGENT.md, SOUL.md, IDENTITY.md, skills/) in the specified directory.",
    responses={
        400: {"description": "Invalid path or path traversal detected"},
    },
)
async def scaffold_agent_pack(
    request: ScaffoldRequest,
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> ScaffoldResponse:
    """Scaffold agent pack files in the specified directory.

    Creates the required Picoclaw template structure:
    - AGENT.md: Main agent definition and behavior
    - SOUL.md: Agent personality and tone
    - IDENTITY.md: Agent identity metadata
    - skills/: Directory for agent skills

    This operation is idempotent - existing files are skipped unless
    overwrite=True is specified.

    Path traversal attempts are rejected for security.
    """
    # Initialize scaffold service
    service = AgentScaffoldService()

    try:
        # Generate scaffold
        entries = service.generate(
            pack_path=request.pack_path,
            overwrite=request.overwrite,
        )

        # Convert to response format
        response_entries = [
            ScaffoldEntry(
                path=str(entry.path),
                entry_type=entry.entry_type.value,
                created=entry.created,
                already_existed=entry.already_existed,
            )
            for entry in entries
        ]

        # Get the resolved path (first entry is the pack directory)
        resolved_path = (
            response_entries[0].path if response_entries else request.pack_path
        )

        # Determine message
        created_count = sum(1 for e in entries if e.created)
        existed_count = sum(1 for e in entries if not e.created and e.already_existed)

        if created_count > 0 and existed_count > 0:
            message = (
                f"Created {created_count} new entries, {existed_count} already existed"
            )
        elif created_count > 0:
            message = f"Created {created_count} scaffold entries successfully"
        else:
            message = (
                "All scaffold entries already exist (use overwrite=True to replace)"
            )

        return ScaffoldResponse(
            success=True,
            pack_path=resolved_path,
            entries=response_entries,
            message=message,
        )

    except Exception as e:
        if "traversal" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Path traversal detected",
                    "message": str(e),
                    "action": "Use a path within the allowed directory",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Scaffold generation failed",
                "message": str(e),
            },
        )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register agent pack",
    description="Register a path-linked agent pack after validating its scaffold structure. Returns checklist errors if validation fails.",
    responses={
        400: {
            "description": "Validation failed with checklist",
            "model": RegisterResponse,
        },
        403: {"description": "Guest mode not allowed"},
    },
)
async def register_agent_pack(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> RegisterResponse:
    """Register an agent pack from a filesystem path.

    Validates the pack at source_path and registers it for the workspace.
    Returns a structured checklist if validation fails, allowing users to
    identify and fix missing or invalid scaffold entries.

    Registration binds to the path - the folder remains the source of truth.
    Future changes are detected as stale and can be revalidated.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Guest mode does not support pack registration",
                "reason": "Guest sessions are ephemeral and do not have persistent packs",
            },
        )

    # Get workspace ID from principal
    workspace_id = getattr(principal, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Could not determine workspace from principal"},
        )

    # Initialize pack service
    service = AgentPackService(session=db)

    try:
        # Register the pack
        result = service.register(
            workspace_id=UUID(workspace_id),
            name=request.name,
            source_path=request.source_path,
        )

        # Convert validation report to response format
        validation_report = ValidationReport(
            is_valid=result.report.is_valid,
            checklist=[
                ChecklistEntry(
                    code=entry.code,
                    path=entry.path,
                    message=entry.message,
                    severity=entry.severity,
                )
                for entry in result.report.checklist
            ],
            source_digest=result.report.source_digest,
            error_count=result.report.error_count,
            warning_count=result.report.warning_count,
        )

        # Return appropriate response based on success
        if result.success:
            return RegisterResponse(
                success=True,
                pack_id=str(result.pack.id) if result.pack else None,
                pack_name=result.pack.name if result.pack else None,
                validation=validation_report,
                errors=result.errors,
            )
        else:
            # Validation failed - return 200 with error details
            # (not 500 - this is expected user-fixable behavior)
            return RegisterResponse(
                success=False,
                pack_id=None,
                pack_name=None,
                validation=validation_report,
                errors=result.errors,
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Registration failed",
                "message": str(e),
            },
        )


@router.post(
    "/{pack_id}/validate",
    response_model=RevalidateResponse,
    summary="Revalidate agent pack",
    description="Re-run validation on a registered agent pack and update its status.",
    responses={
        404: {"description": "Pack not found"},
        403: {"description": "Access denied"},
    },
)
async def revalidate_agent_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> RevalidateResponse:
    """Revalidate a registered agent pack.

    Re-runs validation on the pack's source path and updates its
    validation status and digest. Use this after making changes to
    the pack files to refresh its status.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Guest mode does not support pack revalidation"},
        )

    # Validate pack_id format
    try:
        pack_uuid = UUID(pack_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid pack ID format"},
        )

    # Get workspace ID from principal
    workspace_id = getattr(principal, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Could not determine workspace from principal"},
        )

    # Initialize pack service
    service = AgentPackService(session=db)

    # Verify pack exists and belongs to workspace
    pack = service.get_pack(pack_uuid)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Pack not found"},
        )

    if str(pack.workspace_id) != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Access denied - pack belongs to different workspace"},
        )

    try:
        # Revalidate the pack
        result = service.revalidate(pack_id=pack_uuid)

        # Convert to response format
        validation_report = ValidationReport(
            is_valid=result.report.is_valid,
            checklist=[
                ChecklistEntry(
                    code=entry.code,
                    path=entry.path,
                    message=entry.message,
                    severity=entry.severity,
                )
                for entry in result.report.checklist
            ],
            source_digest=result.report.source_digest,
            error_count=result.report.error_count,
            warning_count=result.report.warning_count,
        )

        return RevalidateResponse(
            success=result.success,
            pack_id=str(pack_id),
            validation=validation_report,
            errors=result.errors,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Revalidation failed",
                "message": str(e),
            },
        )


@router.get(
    "/{pack_id}/stale",
    response_model=StaleCheckResponse,
    summary="Check if pack is stale",
    description="Check if the pack source has changed since registration (stale detection).",
    responses={
        404: {"description": "Pack not found"},
        403: {"description": "Access denied"},
    },
)
async def check_pack_stale(
    pack_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> StaleCheckResponse:
    """Check if pack source is stale.

    Compares the current source digest to the stored digest from
    registration. If stale, the pack status is updated to 'stale'
    and should be revalidated.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Guest mode does not support pack stale checks"},
        )

    # Validate pack_id format
    try:
        pack_uuid = UUID(pack_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid pack ID format"},
        )

    # Get workspace ID from principal
    workspace_id = getattr(principal, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Could not determine workspace from principal"},
        )

    # Initialize pack service
    service = AgentPackService(session=db)

    # Verify pack exists and belongs to workspace
    pack = service.get_pack(pack_uuid)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Pack not found"},
        )

    if str(pack.workspace_id) != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Access denied - pack belongs to different workspace"},
        )

    try:
        # Check if stale
        result = service.check_stale(pack_id=pack_uuid)

        return StaleCheckResponse(
            is_stale=result.is_stale,
            current_digest=result.current_digest,
            stored_digest=result.stored_digest,
            pack_id=str(pack_id),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Stale check failed",
                "message": str(e),
            },
        )


@router.get(
    "/{pack_id}",
    response_model=PackStatusResponse,
    summary="Get pack status",
    description="Get the current status of an agent pack.",
    responses={
        404: {"description": "Pack not found"},
        403: {"description": "Access denied"},
    },
)
async def get_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> PackStatusResponse:
    """Get agent pack status.

    Returns pack metadata, validation status, and last validation time.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Guest mode does not support pack retrieval"},
        )

    # Validate pack_id format
    try:
        pack_uuid = UUID(pack_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid pack ID format"},
        )

    # Get workspace ID from principal
    workspace_id = getattr(principal, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Could not determine workspace from principal"},
        )

    # Initialize pack service
    service = AgentPackService(session=db)

    # Get pack
    pack = service.get_pack(pack_uuid)

    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Pack not found"},
        )

    # Verify workspace ownership
    if str(pack.workspace_id) != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Access denied - pack belongs to different workspace"},
        )

    # Handle validation_status - could be enum (PostgreSQL) or string (SQLite)
    if pack.validation_status:
        if hasattr(pack.validation_status, "value"):
            validation_status = pack.validation_status.value
        else:
            validation_status = str(pack.validation_status)
    else:
        validation_status = "pending"

    return PackStatusResponse(
        pack_id=str(pack.id),
        name=pack.name,
        source_path=pack.source_path,
        validation_status=validation_status,
        is_active=pack.is_active,
        last_validated_at=pack.last_validated_at.isoformat()
        if pack.last_validated_at
        else None,
    )


@router.get(
    "",
    response_model=List[PackStatusResponse],
    summary="List agent packs",
    description="List all agent packs for the current workspace.",
    responses={
        403: {"description": "Guest mode not allowed"},
    },
)
async def list_packs(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    principal: AnyPrincipal = Depends(resolve_principal_or_guest),
) -> List[PackStatusResponse]:
    """List agent packs for the workspace.

    Returns all registered agent packs with their status.
    """
    # Check if guest mode
    if is_guest_principal(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Guest mode does not support pack listing"},
        )

    # Get workspace ID from principal
    workspace_id = getattr(principal, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Could not determine workspace from principal"},
        )

    # Initialize pack service
    service = AgentPackService(session=db)

    # List packs
    packs = service.list_workspace_packs(
        workspace_id=UUID(workspace_id),
        include_inactive=include_inactive,
    )

    return [
        PackStatusResponse(
            pack_id=str(pack.id),
            name=pack.name,
            source_path=pack.source_path,
            validation_status=(
                pack.validation_status.value
                if hasattr(pack.validation_status, "value")
                else str(pack.validation_status)
            )
            if pack.validation_status
            else "pending",
            is_active=pack.is_active,
            last_validated_at=pack.last_validated_at.isoformat()
            if pack.last_validated_at
            else None,
        )
        for pack in packs
    ]
