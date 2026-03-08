"""Agent pack service for registration and lifecycle management.

Provides path-linked pack registration, validation, and stale detection.
Uses AgentPackRepository for all persistence operations.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.db.repositories.agent_pack_repository import AgentPackRepository
from src.db.models import AgentPack, AgentPackValidationStatus
from src.services.agent_pack_validation import (
    AgentPackValidationService,
    ValidationReport,
)


@dataclass
class RegistrationResult:
    """Result of agent pack registration attempt.

    Attributes:
        success: True if registration succeeded
        pack: The AgentPack if registered, None otherwise
        report: Validation report with checklist
        errors: List of error messages if registration failed
    """

    success: bool
    pack: Optional[AgentPack]
    report: ValidationReport
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "pack_id": str(self.pack.id) if self.pack else None,
            "pack_name": self.pack.name if self.pack else None,
            "validation": self.report.to_dict(),
            "errors": self.errors,
        }


@dataclass
class StaleCheckResult:
    """Result of stale source check.

    Attributes:
        is_stale: True if source has changed
        current_digest: Current computed digest
        stored_digest: Previously stored digest
        pack_id: ID of the pack checked
    """

    is_stale: bool
    current_digest: Optional[str]
    stored_digest: Optional[str]
    pack_id: UUID

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_stale": self.is_stale,
            "current_digest": self.current_digest,
            "stored_digest": self.stored_digest,
            "pack_id": str(self.pack_id),
        }


class AgentPackServiceError(Exception):
    """Base error for agent pack service operations."""

    pass


class AgentPackService:
    """Service for agent pack registration and lifecycle.

    Manages path-linked pack registration with validation integration.
    All persistence operations go through AgentPackRepository.
    """

    def __init__(
        self,
        session: Session,
        repository: Optional[AgentPackRepository] = None,
        validation_service: Optional[AgentPackValidationService] = None,
    ):
        """Initialize pack service.

        Args:
            session: SQLAlchemy database session
            repository: Optional repository instance (created if not provided)
            validation_service: Optional validation service (created if not provided)
        """
        self._session = session
        self._repository = repository or AgentPackRepository(session)
        self._validation = validation_service or AgentPackValidationService()

    def _normalize_path(self, source_path: str) -> str:
        """Normalize source path for consistent storage.

        Args:
            source_path: Raw source path

        Returns:
            Normalized absolute path string
        """
        path = Path(source_path)

        # Resolve to absolute path
        if not path.is_absolute():
            path = Path.cwd() / path

        # Resolve .. and . segments
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            # If resolution fails, use absolute path
            resolved = path.absolute()

        return str(resolved)

    def register(
        self,
        workspace_id: UUID,
        name: str,
        source_path: str,
    ) -> RegistrationResult:
        """Register or update an agent pack.

        Validates the pack at source_path before registration.
        Invalid packs return checklist without persistence.
        Valid packs are upserted with validation status and digest.

        Args:
            workspace_id: UUID of the owning workspace
            name: Human-readable name for the pack
            source_path: Filesystem path to the pack folder

        Returns:
            RegistrationResult with success status and validation report
        """
        # Normalize source path
        normalized_path = self._normalize_path(source_path)

        # Validate the pack
        report = self._validation.validate(normalized_path, compute_digest=True)

        # If validation failed, return without persistence
        if not report.is_valid:
            return RegistrationResult(
                success=False,
                pack=None,
                report=report,
                errors=[f"Validation failed with {report.error_count} error(s)"],
            )

        # Check if pack already exists for this workspace+path
        existing_pack = self._repository.get_by_workspace_and_path(workspace_id, normalized_path)

        try:
            if existing_pack:
                # Update existing pack
                pack = self._update_existing_pack(existing_pack, name, report)
            else:
                # Create new pack
                pack = self._create_new_pack(workspace_id, name, normalized_path, report)

            return RegistrationResult(
                success=True,
                pack=pack,
                report=report,
                errors=[],
            )

        except Exception as e:
            return RegistrationResult(
                success=False,
                pack=None,
                report=report,
                errors=[f"Persistence error: {str(e)}"],
            )

    def _create_new_pack(
        self,
        workspace_id: UUID,
        name: str,
        source_path: str,
        report: ValidationReport,
    ) -> AgentPack:
        """Create a new agent pack record.

        Uses repository create method for persistence.

        Args:
            workspace_id: UUID of the owning workspace
            name: Human-readable name for the pack
            source_path: Normalized source path
            report: Validation report with digest

        Returns:
            Created AgentPack
        """
        # Create through repository
        pack = self._repository.create(
            workspace_id=workspace_id,
            name=name,
            source_path=source_path,
            source_digest=report.source_digest,
        )

        # Update validation status through repository
        self._repository.update_validation_status(
            pack_id=pack.id,
            status=AgentPackValidationStatus.VALID,
            report_json=report.to_json(),
        )

        # Refresh to get updated fields
        self._session.refresh(pack)

        return pack

    def _update_existing_pack(
        self,
        pack: AgentPack,
        name: str,
        report: ValidationReport,
    ) -> AgentPack:
        """Update an existing agent pack record.

        Uses repository methods for persistence.

        Args:
            pack: Existing AgentPack to update
            name: Updated name
            report: Validation report with digest

        Returns:
            Updated AgentPack
        """
        # Update name
        pack.name = name

        # Update source digest through repository
        self._repository.update_source_digest(
            pack_id=pack.id,
            source_digest=report.source_digest or "",
            mark_stale=False,  # We're updating it now, so not stale
        )

        # Update validation status through repository
        self._repository.update_validation_status(
            pack_id=pack.id,
            status=AgentPackValidationStatus.VALID,
            report_json=report.to_json(),
        )

        # Refresh to get updated fields
        self._session.refresh(pack)

        return pack

    def revalidate(
        self,
        pack_id: UUID,
    ) -> RegistrationResult:
        """Re-validate a registered pack and update status.

        Re-runs validation on the source path and updates
        the pack's validation status and digest.

        Args:
            pack_id: UUID of the pack to revalidate

        Returns:
            RegistrationResult with updated status
        """
        # Get the pack
        pack = self._repository.get_by_id(pack_id)

        if not pack:
            return RegistrationResult(
                success=False,
                pack=None,
                report=ValidationReport(
                    is_valid=False,
                    checklist=[],
                    source_digest=None,
                    error_count=0,
                    warning_count=0,
                ),
                errors=[f"Pack not found: {pack_id}"],
            )

        # Re-validate the source path
        report = self._validation.validate(
            pack.source_path,
            compute_digest=True,
        )

        # Update status based on validation result
        if report.is_valid:
            status = AgentPackValidationStatus.VALID
        else:
            status = AgentPackValidationStatus.INVALID

        try:
            # Update validation status through repository
            self._repository.update_validation_status(
                pack_id=pack.id,
                status=status,
                report_json=report.to_json(),
            )

            # Update source digest through repository
            if report.source_digest:
                self._repository.update_source_digest(
                    pack_id=pack.id,
                    source_digest=report.source_digest,
                    mark_stale=False,
                )

            # Refresh to get updated fields
            self._session.refresh(pack)

            return RegistrationResult(
                success=report.is_valid,
                pack=pack if report.is_valid else None,
                report=report,
                errors=[]
                if report.is_valid
                else [f"Validation failed with {report.error_count} error(s)"],
            )

        except Exception as e:
            return RegistrationResult(
                success=False,
                pack=pack,
                report=report,
                errors=[f"Update error: {str(e)}"],
            )

    def check_stale(
        self,
        pack_id: UUID,
    ) -> StaleCheckResult:
        """Check if pack source has changed since registration.

        Compares current source digest to stored digest.
        If stale, updates pack status to STALE through repository.

        Args:
            pack_id: UUID of the pack to check

        Returns:
            StaleCheckResult with comparison details
        """
        pack = self._repository.get_by_id(pack_id)

        if not pack:
            raise AgentPackServiceError(f"Pack not found: {pack_id}")

        # Compute current digest
        current_digest = self._validation.compute_digest(pack.source_path)

        # Compare to stored digest
        is_stale = False
        if current_digest and pack.source_digest:
            is_stale = current_digest != pack.source_digest
        elif current_digest and not pack.source_digest:
            # Has content now but didn't before
            is_stale = True

        # If stale, update status through repository
        if is_stale:
            self._repository.update_validation_status(
                pack_id=pack.id,
                status=AgentPackValidationStatus.STALE,
                report_json=json.dumps(
                    {
                        "stale_detected": True,
                        "stored_digest": pack.source_digest,
                        "current_digest": current_digest,
                    }
                ),
            )
            self._session.refresh(pack)

        return StaleCheckResult(
            is_stale=is_stale,
            current_digest=current_digest,
            stored_digest=pack.source_digest,
            pack_id=pack.id,
        )

    def get_pack(self, pack_id: UUID) -> Optional[AgentPack]:
        """Get a pack by ID.

        Args:
            pack_id: UUID of the pack

        Returns:
            AgentPack if found, None otherwise
        """
        return self._repository.get_by_id(pack_id)

    def get_pack_by_path(
        self,
        workspace_id: UUID,
        source_path: str,
    ) -> Optional[AgentPack]:
        """Get a pack by workspace and source path.

        Args:
            workspace_id: UUID of the workspace
            source_path: Source path to look up

        Returns:
            AgentPack if found, None otherwise
        """
        normalized_path = self._normalize_path(source_path)
        return self._repository.get_by_workspace_and_path(workspace_id, normalized_path)

    def list_workspace_packs(
        self,
        workspace_id: UUID,
        include_inactive: bool = False,
    ) -> List[AgentPack]:
        """List packs for a workspace.

        Args:
            workspace_id: UUID of the workspace
            include_inactive: If True, include inactive packs

        Returns:
            List of AgentPack records
        """
        return self._repository.list_by_workspace(
            workspace_id,
            include_inactive=include_inactive,
        )

    def list_stale_packs(
        self,
        workspace_id: Optional[UUID] = None,
    ) -> List[AgentPack]:
        """List packs marked as stale.

        Args:
            workspace_id: Optional workspace filter

        Returns:
            List of stale AgentPack records
        """
        return self._repository.list_stale_packs(workspace_id)

    def set_pack_active(
        self,
        pack_id: UUID,
        is_active: bool,
    ) -> Optional[AgentPack]:
        """Set pack active/inactive status.

        Args:
            pack_id: UUID of the pack
            is_active: New active status

        Returns:
            Updated AgentPack if found, None otherwise
        """
        return self._repository.set_active(pack_id, is_active)
