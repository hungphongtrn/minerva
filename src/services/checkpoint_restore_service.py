"""Checkpoint restore service with fallback and retry policy.

Provides cold-start restore behavior with deterministic fallback:
1. Active checkpoint first
2. Previous valid checkpoint if active fails
3. Single retry on transient failure
4. Fresh-start escape hatch after repeated failure

All outcomes are auditable via audit events.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.db.models import CheckpointState
from src.db.repositories.workspace_checkpoint_repository import (
    WorkspaceCheckpointRepository,
)
from src.db.repositories.audit_event_repository import AuditEventRepository
from src.services.workspace_checkpoint_service import WorkspaceCheckpointService


class RestoreOutcome(Enum):
    """Possible outcomes of a restore operation."""

    SUCCESS = auto()  # Successfully restored from checkpoint
    FALLBACK_SUCCESS = auto()  # Restored from fallback checkpoint
    FRESH_START = auto()  # Started fresh after restore failure
    IN_PROGRESS = auto()  # Restore is currently in progress
    FAILED = auto()  # Restore failed (terminal)


@dataclass
class RestoreResult:
    """Result of a checkpoint restore operation."""

    outcome: RestoreOutcome
    workspace_id: UUID
    checkpoint_id: Optional[str] = None  # Checkpoint that was restored (if any)
    fallback_checkpoint_id: Optional[str] = None  # Fallback checkpoint used
    error_message: Optional[str] = None  # Error details if failed
    restored_data: Optional[Dict[str, Any]] = None  # Restored session/memory state
    fresh_start: bool = False  # True if started fresh (no checkpoint data)
    audit_event_id: Optional[UUID] = None  # ID of audit event created


class CheckpointRestoreError(Exception):
    """Exception for checkpoint restore failures."""

    def __init__(
        self,
        message: str,
        workspace_id: Optional[UUID] = None,
        checkpoint_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.workspace_id = workspace_id
        self.checkpoint_id = checkpoint_id


class ManifestValidationError(CheckpointRestoreError):
    """Exception for manifest validation failures."""

    pass


class ArchiveValidationError(CheckpointRestoreError):
    """Exception for archive checksum validation failures."""

    pass


class CheckpointRestoreService:
    """Service for checkpoint restore operations with fallback and retry.

    Implements the cold-start restore behavior:
    1. Attempt to restore from active checkpoint
    2. If active fails, fall back to previous valid checkpoint
    3. Retry once on transient failures
    4. Fall back to fresh start after two failures

    All outcomes are logged to the audit trail.
    """

    MAX_RETRY_ATTEMPTS = 2  # Initial attempt + one retry
    FALLBACK_MAX_DEPTH = 3  # Maximum fallback chain depth

    def __init__(
        self,
        session: Session,
        checkpoint_repository: Optional[WorkspaceCheckpointRepository] = None,
        audit_repository: Optional[AuditEventRepository] = None,
        checkpoint_service: Optional[WorkspaceCheckpointService] = None,
    ):
        """Initialize the restore service.

        Args:
            session: SQLAlchemy session for database operations.
            checkpoint_repository: Optional checkpoint repository.
            audit_repository: Optional audit event repository.
            checkpoint_service: Optional checkpoint service for storage operations.
        """
        self._session = session
        self._checkpoint_repo = checkpoint_repository or WorkspaceCheckpointRepository(
            session
        )
        self._audit_repo = audit_repository or AuditEventRepository(session)
        self._checkpoint_service = checkpoint_service

    async def restore_workspace(
        self,
        workspace_id: UUID,
        actor_id: Optional[str] = None,
        attempt_restore: bool = True,
    ) -> RestoreResult:
        """Restore workspace from checkpoint with fallback policy.

        This is the main entrypoint for cold-start restore. It:
        1. Resolves the active checkpoint pointer
        2. Validates and restores the checkpoint
        3. Falls back to previous valid checkpoint on failure
        4. Retries once on transient failure
        5. Returns fresh-start outcome after repeated failures

        Args:
            workspace_id: UUID of the workspace to restore.
            actor_id: Optional identifier of the actor triggering restore.
            attempt_restore: If False, skip restore and return fresh start.

        Returns:
            RestoreResult with outcome and restored data (if any).
        """
        if not attempt_restore:
            # Fresh start requested explicitly
            audit_event = self._audit_repo.log_checkpoint_management(
                workspace_id=workspace_id,
                checkpoint_id="none",
                action="fresh_start_explicit",
                outcome="success",
                actor_id=actor_id,
                reason="Restore explicitly disabled",
            )
            return RestoreResult(
                outcome=RestoreOutcome.FRESH_START,
                workspace_id=workspace_id,
                fresh_start=True,
                audit_event_id=audit_event.id,
            )

        # Step 1: Get active checkpoint
        active_checkpoint = self._checkpoint_repo.get_active_checkpoint(workspace_id)

        if not active_checkpoint:
            # No active checkpoint - fresh start
            audit_event = self._audit_repo.log_checkpoint_management(
                workspace_id=workspace_id,
                checkpoint_id="none",
                action="fresh_start_no_checkpoint",
                outcome="success",
                actor_id=actor_id,
                reason="No active checkpoint configured",
            )
            return RestoreResult(
                outcome=RestoreOutcome.FRESH_START,
                workspace_id=workspace_id,
                fresh_start=True,
                audit_event_id=audit_event.id,
            )

        # Step 2: Attempt restore from active checkpoint (with retry)
        result = await self._attempt_restore_with_retry(
            workspace_id=workspace_id,
            checkpoint=active_checkpoint,
            actor_id=actor_id,
            is_fallback=False,
        )

        if result.outcome in (RestoreOutcome.SUCCESS, RestoreOutcome.IN_PROGRESS):
            return result

        # Step 3: Active checkpoint failed - try fallback chain
        fallback_result = await self._attempt_fallback_restore(
            workspace_id=workspace_id,
            failed_checkpoint=active_checkpoint,
            actor_id=actor_id,
        )

        if fallback_result:
            return fallback_result

        # Step 4: All attempts failed - fresh start
        audit_event = self._audit_repo.log_checkpoint_management(
            workspace_id=workspace_id,
            checkpoint_id=active_checkpoint.checkpoint_id,
            action="fresh_start_after_failure",
            outcome="failure",
            actor_id=actor_id,
            reason="All restore attempts failed, falling back to fresh start",
            payload_json=json.dumps(
                {
                    "active_checkpoint_id": str(active_checkpoint.id),
                    "active_checkpoint_uuid": active_checkpoint.checkpoint_id,
                }
            ),
        )

        return RestoreResult(
            outcome=RestoreOutcome.FRESH_START,
            workspace_id=workspace_id,
            checkpoint_id=active_checkpoint.checkpoint_id,
            fresh_start=True,
            error_message="All checkpoint restore attempts failed",
            audit_event_id=audit_event.id,
        )

    async def _attempt_restore_with_retry(
        self,
        workspace_id: UUID,
        checkpoint: Any,  # WorkspaceCheckpoint
        actor_id: Optional[str],
        is_fallback: bool = False,
    ) -> RestoreResult:
        """Attempt to restore from a checkpoint with single retry on failure.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint: Checkpoint to restore from.
            actor_id: Optional actor identifier.
            is_fallback: Whether this is a fallback checkpoint attempt.

        Returns:
            RestoreResult with outcome.
        """
        last_error = None

        for attempt in range(1, self.MAX_RETRY_ATTEMPTS + 1):
            try:
                result = await self._do_restore(
                    workspace_id=workspace_id,
                    checkpoint=checkpoint,
                    actor_id=actor_id,
                    is_fallback=is_fallback,
                    attempt_number=attempt,
                )

                if result.outcome in (
                    RestoreOutcome.SUCCESS,
                    RestoreOutcome.FALLBACK_SUCCESS,
                ):
                    return result

            except (ManifestValidationError, ArchiveValidationError) as e:
                # Validation errors are not retryable
                last_error = str(e)
                self._audit_repo.log_checkpoint_management(
                    workspace_id=workspace_id,
                    checkpoint_id=checkpoint.checkpoint_id,
                    action="restore_validation_failed",
                    outcome="failure",
                    actor_id=actor_id,
                    reason=f"Validation failed (attempt {attempt}): {e}",
                )
                # Don't retry validation errors
                break

            except Exception as e:
                # Transient error - may retry
                last_error = str(e)
                if attempt < self.MAX_RETRY_ATTEMPTS:
                    # Log retry attempt
                    self._audit_repo.log_checkpoint_management(
                        workspace_id=workspace_id,
                        checkpoint_id=checkpoint.checkpoint_id,
                        action="restore_retry",
                        outcome="failure",
                        actor_id=actor_id,
                        reason=f"Transient error, will retry: {e}",
                    )
                else:
                    # Final attempt failed
                    self._audit_repo.log_checkpoint_management(
                        workspace_id=workspace_id,
                        checkpoint_id=checkpoint.checkpoint_id,
                        action="restore_failed",
                        outcome="failure",
                        actor_id=actor_id,
                        reason=f"All attempts failed: {e}",
                    )

        # All attempts failed
        return RestoreResult(
            outcome=RestoreOutcome.FAILED,
            workspace_id=workspace_id,
            checkpoint_id=checkpoint.checkpoint_id,
            error_message=last_error or "Restore failed after all retry attempts",
        )

    async def _do_restore(
        self,
        workspace_id: UUID,
        checkpoint: Any,  # WorkspaceCheckpoint
        actor_id: Optional[str],
        is_fallback: bool = False,
        attempt_number: int = 1,
    ) -> RestoreResult:
        """Perform actual restore from a checkpoint.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint: Checkpoint to restore from.
            actor_id: Optional actor identifier.
            is_fallback: Whether this is a fallback checkpoint.
            attempt_number: Which attempt this is (1-indexed).

        Returns:
            RestoreResult with outcome.
        """
        checkpoint_id = checkpoint.checkpoint_id

        # Step 1: Validate checkpoint state
        checkpoint_state = (
            checkpoint.state.value
            if hasattr(checkpoint.state, "value")
            else str(checkpoint.state).lower()
        )
        if checkpoint_state != CheckpointState.COMPLETED:
            raise ManifestValidationError(
                f"Checkpoint {checkpoint_id} is not in COMPLETED state (state: {checkpoint.state})",
                workspace_id=workspace_id,
                checkpoint_id=checkpoint_id,
            )

        # Step 2: Parse and validate manifest
        manifest = self._parse_manifest(checkpoint.manifest_json)
        self._validate_manifest(manifest, checkpoint_id)

        # Step 3: Validate archive checksum (if checkpoint service available)
        if self._checkpoint_service and checkpoint.storage_key:
            # In production, this would download and verify the archive
            # For now, we simulate validation success
            pass

        # Step 4: Extract restored data from manifest
        restored_data = self._extract_restore_data(manifest)

        # Step 5: Log success
        action = "restore_fallback" if is_fallback else "restore"
        audit_event = self._audit_repo.log_checkpoint_management(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            action=action,
            outcome="success",
            actor_id=actor_id,
            reason=f"Restored successfully (attempt {attempt_number})",
            payload_json=json.dumps(
                {
                    "checkpoint_db_id": str(checkpoint.id),
                    "checkpoint_uuid": checkpoint_id,
                    "is_fallback": is_fallback,
                    "attempt": attempt_number,
                    "has_session_data": restored_data is not None,
                }
            ),
        )

        outcome = (
            RestoreOutcome.FALLBACK_SUCCESS if is_fallback else RestoreOutcome.SUCCESS
        )

        return RestoreResult(
            outcome=outcome,
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            restored_data=restored_data,
            audit_event_id=audit_event.id,
        )

    async def _attempt_fallback_restore(
        self,
        workspace_id: UUID,
        failed_checkpoint: Any,  # WorkspaceCheckpoint
        actor_id: Optional[str],
    ) -> Optional[RestoreResult]:
        """Attempt to restore from fallback checkpoints in the chain.

        Args:
            workspace_id: UUID of the workspace.
            failed_checkpoint: The checkpoint that failed to restore.
            actor_id: Optional actor identifier.

        Returns:
            RestoreResult if fallback succeeds, None if all fail.
        """
        # Get fallback chain
        chain = self._checkpoint_repo.get_fallback_chain(
            failed_checkpoint.id,
            max_depth=self.FALLBACK_MAX_DEPTH,
        )

        # Skip the first entry (the failed checkpoint itself)
        fallback_candidates = chain[1:] if len(chain) > 1 else []

        if not fallback_candidates and failed_checkpoint.previous_checkpoint_id:
            previous_checkpoint = self._checkpoint_repo.get_by_id(
                failed_checkpoint.previous_checkpoint_id
            )
            if previous_checkpoint:
                fallback_candidates = [previous_checkpoint]

        for fallback_checkpoint in fallback_candidates:
            # Skip if not completed
            fallback_state = (
                fallback_checkpoint.state.value
                if hasattr(fallback_checkpoint.state, "value")
                else str(fallback_checkpoint.state).lower()
            )
            if fallback_state != CheckpointState.COMPLETED:
                continue

            # Log fallback attempt
            self._audit_repo.log_checkpoint_management(
                workspace_id=workspace_id,
                checkpoint_id=failed_checkpoint.checkpoint_id,
                action="restore_fallback_attempt",
                outcome="success",
                actor_id=actor_id,
                reason=f"Attempting fallback to {fallback_checkpoint.checkpoint_id}",
                payload_json=json.dumps(
                    {
                        "failed_checkpoint_id": str(failed_checkpoint.id),
                        "fallback_checkpoint_id": str(fallback_checkpoint.id),
                        "fallback_checkpoint_uuid": fallback_checkpoint.checkpoint_id,
                    }
                ),
            )

            # Attempt restore from fallback
            result = await self._attempt_restore_with_retry(
                workspace_id=workspace_id,
                checkpoint=fallback_checkpoint,
                actor_id=actor_id,
                is_fallback=True,
            )

            if result.outcome in (
                RestoreOutcome.SUCCESS,
                RestoreOutcome.FALLBACK_SUCCESS,
            ):
                result.outcome = RestoreOutcome.FALLBACK_SUCCESS
                result.fallback_checkpoint_id = fallback_checkpoint.checkpoint_id
                result.checkpoint_id = failed_checkpoint.checkpoint_id
                return result

        # No fallback succeeded
        return None

    def _parse_manifest(self, manifest_json: Optional[str]) -> Dict[str, Any]:
        """Parse manifest JSON string.

        Args:
            manifest_json: JSON string of the manifest.

        Returns:
            Parsed manifest dict.

        Raises:
            ManifestValidationError: If manifest is invalid.
        """
        if not manifest_json:
            raise ManifestValidationError("Manifest is empty or None")

        try:
            manifest = json.loads(manifest_json)
        except json.JSONDecodeError as e:
            raise ManifestValidationError(f"Invalid JSON in manifest: {e}")

        return manifest

    def _validate_manifest(self, manifest: Dict[str, Any], checkpoint_id: str) -> None:
        """Validate checkpoint manifest.

        Args:
            manifest: Parsed manifest dict.
            checkpoint_id: Checkpoint identifier for error messages.

        Raises:
            ManifestValidationError: If manifest is invalid.
        """
        # Required fields
        required_fields = ["checkpoint_id", "version", "created_at"]
        for field in required_fields:
            if field not in manifest:
                raise ManifestValidationError(
                    f"Manifest missing required field: {field}",
                    checkpoint_id=checkpoint_id,
                )

        # Validate checkpoint_id matches
        if manifest.get("checkpoint_id") != checkpoint_id:
            raise ManifestValidationError(
                f"Manifest checkpoint_id mismatch: {manifest.get('checkpoint_id')} != {checkpoint_id}",
                checkpoint_id=checkpoint_id,
            )

        # Validate version format (semver-like)
        version = manifest.get("version", "")
        if not version or not isinstance(version, str):
            raise ManifestValidationError(
                "Manifest version is invalid",
                checkpoint_id=checkpoint_id,
            )

    def _extract_restore_data(
        self, manifest: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract restore data from manifest.

        Args:
            manifest: Parsed manifest dict.

        Returns:
            Dict with session/memory state if present, None otherwise.
        """
        # In production, this would extract the actual session/memory state
        # from the manifest or the archive contents
        restore_data = {}

        # Check for session data in manifest
        if "session_data" in manifest:
            restore_data["session"] = manifest["session_data"]

        if "memory_state" in manifest:
            restore_data["memory"] = manifest["memory_state"]

        return restore_data if restore_data else None

    def validate_archive_checksum(
        self,
        checkpoint_id: str,
        expected_checksum: str,
        archive_data: bytes,
    ) -> bool:
        """Validate archive checksum against expected value.

        Args:
            checkpoint_id: Checkpoint identifier.
            expected_checksum: Expected SHA-256 checksum.
            archive_data: Archive bytes to validate.

        Returns:
            True if checksum matches.

        Raises:
            ArchiveValidationError: If checksum doesn't match.
        """
        actual_checksum = hashlib.sha256(archive_data).hexdigest()

        if actual_checksum != expected_checksum:
            raise ArchiveValidationError(
                f"Checksum mismatch for checkpoint {checkpoint_id}: "
                f"expected {expected_checksum}, got {actual_checksum}",
                checkpoint_id=checkpoint_id,
            )

        return True

    async def check_restore_status(
        self,
        workspace_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Check the status of a restore operation.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Dict with restore status if in progress, None otherwise.
        """
        # This would check the actual restore status in a production system
        # For now, return None (not in progress)
        return None
