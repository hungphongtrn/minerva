"""Workspace checkpoint service for checkpoint write operations.

Provides checkpoint creation with S3 storage integration,
active pointer management, and audit logging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.db.models import (
    CheckpointState,
    AuditEventCategory,
)
from src.db.repositories.workspace_checkpoint_repository import (
    WorkspaceCheckpointRepository,
)
from src.db.repositories.audit_event_repository import AuditEventRepository
from src.services.checkpoint_archive_service import (
    CheckpointArchiveService,
    SessionState,
)

if TYPE_CHECKING:
    from src.infrastructure.checkpoints.s3_checkpoint_store import (
        S3CheckpointStore,
        CheckpointManifest,
    )


class CheckpointPersistenceError(Exception):
    """Raised when checkpoint persistence fails."""

    pass


class GuestCheckpointError(Exception):
    """Raised when guest mode tries to create checkpoints."""

    pass


class PointerUpdateForbiddenError(Exception):
    """Raised when non-operator attempts to update checkpoint pointer."""

    pass


class PointerRollbackForbiddenError(Exception):
    """Raised when attempting to rollback to older checkpoint revision."""

    pass


class WorkspaceCheckpointService:
    """Service for workspace checkpoint write operations.

    This service handles checkpoint lifecycle:
    - Creates checkpoint records in database
    - Archives session state and stores to S3
    - Manages active checkpoint pointer
    - Appends audit events for all operations

    Checkpoint creation is a two-phase process:
    1. Create DB record in PENDING state
    2. Archive and store to S3
    3. Mark COMPLETED and advance active pointer

    Guest runs cannot create checkpoints - they are explicitly
    non-persistent by design.
    """

    # Checkpoint format version
    CHECKPOINT_VERSION = "1.0.0"

    def __init__(
        self,
        session: Session,
        checkpoint_repo: Optional[WorkspaceCheckpointRepository] = None,
        audit_repo: Optional[AuditEventRepository] = None,
        archive_service: Optional[CheckpointArchiveService] = None,
        store: Optional[S3CheckpointStore] = None,
    ):
        """Initialize checkpoint service.

        Args:
            session: Database session for persistence operations.
            checkpoint_repo: Optional WorkspaceCheckpointRepository.
            audit_repo: Optional AuditEventRepository.
            archive_service: Optional CheckpointArchiveService.
            store: Optional S3 checkpoint store (required for full persistence).
        """
        self._session = session
        self._checkpoint_repo = checkpoint_repo or WorkspaceCheckpointRepository(
            session
        )
        self._audit_repo = audit_repo or AuditEventRepository(session)
        self._archive_service = archive_service or CheckpointArchiveService(store)
        self._store = store

    def create_checkpoint(
        self,
        workspace_id: UUID,
        agent_pack_id: UUID,
        session_state: SessionState,
        created_by_run_id: Optional[str] = None,
        is_guest: bool = False,
        principal_id: Optional[str] = None,
        auto_advance_active: bool = True,
    ) -> dict[str, Any]:
        """Create a checkpoint with full persistence.

        Creates checkpoint archive, stores to S3, creates DB record,
        and optionally advances the active checkpoint pointer.

        Args:
            workspace_id: UUID of the workspace.
            agent_pack_id: UUID of the agent pack.
            session_state: Runtime session state to checkpoint.
            created_by_run_id: Optional run ID that created this checkpoint.
            is_guest: Whether this is a guest execution.
            principal_id: Optional actor ID for audit.
            auto_advance_active: If True, advance active pointer on success.

        Returns:
            Dict with checkpoint_id, state, and metadata.

        Raises:
            GuestCheckpointError: If is_guest=True.
            CheckpointPersistenceError: If storage fails.
        """
        if is_guest:
            raise GuestCheckpointError(
                "Guest runs cannot create checkpoints. "
                "Authenticate with an API key to enable checkpoint persistence."
            )

        if not self._store:
            raise CheckpointPersistenceError(
                "S3CheckpointStore not configured - cannot persist checkpoint"
            )

        # Generate checkpoint ID
        checkpoint_uuid = uuid4()
        checkpoint_id = str(checkpoint_uuid)

        # Get previous checkpoint for fallback chain
        previous_checkpoint = self._checkpoint_repo.get_previous_completed_checkpoint(
            workspace_id
        )
        previous_checkpoint_id = previous_checkpoint.id if previous_checkpoint else None

        # Create archive
        try:
            archive_result = self._archive_service.create_checkpoint(
                workspace_id=workspace_id,
                agent_pack_id=agent_pack_id,
                session_state=session_state,
                checkpoint_id=checkpoint_uuid,
            )
        except Exception as e:
            raise CheckpointPersistenceError(
                f"Failed to create checkpoint archive: {e}"
            ) from e

        # Store to S3
        try:
            self._store.put_archive(
                workspace_id=workspace_id,
                checkpoint_id=checkpoint_uuid,
                archive_bytes=archive_result.archive_bytes,
                manifest=archive_result.manifest,
            )
        except Exception as e:
            raise CheckpointPersistenceError(f"Failed to store checkpoint: {e}") from e

        # Create storage key
        storage_key = self._get_storage_key(workspace_id, checkpoint_uuid)

        # Create DB record
        checkpoint = self._checkpoint_repo.create(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            version=self.CHECKPOINT_VERSION,
            storage_key=storage_key,
            created_by_run_id=created_by_run_id,
            previous_checkpoint_id=previous_checkpoint_id,
            manifest_json=self._serialize_manifest(archive_result.manifest),
        )

        # Mark as completed
        self._checkpoint_repo.mark_completed(
            checkpoint_db_id=checkpoint.id,
            storage_size_bytes=len(archive_result.archive_bytes),
        )

        # Advance active pointer if requested
        if auto_advance_active:
            self._checkpoint_repo.advance_active_checkpoint(
                workspace_id=workspace_id,
                checkpoint_id=checkpoint.id,
                changed_by=principal_id or "checkpoint_service",
            )

        # Audit log
        self._audit_repo.log_checkpoint_management(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            action="created",
            outcome="success",
            actor_id=principal_id,
            payload_json=self._serialize_manifest(archive_result.manifest),
        )

        return {
            "checkpoint_id": checkpoint_id,
            "checkpoint_db_id": str(checkpoint.id),
            "state": "completed",
            "workspace_id": str(workspace_id),
            "agent_pack_id": str(agent_pack_id),
            "storage_key": storage_key,
            "storage_size_bytes": len(archive_result.archive_bytes),
            "previous_checkpoint_id": str(previous_checkpoint_id)
            if previous_checkpoint_id
            else None,
        }

    def create_checkpoint_metadata_only(
        self,
        workspace_id: UUID,
        checkpoint_id: str,
        storage_key: str,
        version: str,
        created_by_run_id: Optional[str] = None,
        is_guest: bool = False,
        principal_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create checkpoint DB record without S3 storage.

        Used for testing or when storage is handled externally.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: Unique checkpoint identifier.
            storage_key: Storage location key.
            version: Checkpoint format version.
            created_by_run_id: Optional run ID that created this checkpoint.
            is_guest: Whether this is a guest execution.
            principal_id: Optional actor ID for audit.

        Returns:
            Dict with checkpoint_id and metadata.

        Raises:
            GuestCheckpointError: If is_guest=True.
        """
        if is_guest:
            raise GuestCheckpointError("Guest runs cannot create checkpoints.")

        # Create DB record
        checkpoint = self._checkpoint_repo.create(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            version=version,
            storage_key=storage_key,
            created_by_run_id=created_by_run_id,
        )

        # Mark as completed
        self._checkpoint_repo.mark_completed(checkpoint.id)

        # Advance active pointer
        self._checkpoint_repo.advance_active_checkpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint.id,
            changed_by=principal_id or "checkpoint_service",
        )

        # Audit log
        self._audit_repo.log_checkpoint_management(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_id,
            action="created",
            outcome="success",
            actor_id=principal_id,
        )

        return {
            "checkpoint_id": checkpoint_id,
            "checkpoint_db_id": str(checkpoint.id),
            "state": "completed",
            "workspace_id": str(workspace_id),
        }

    def advance_active_checkpoint(
        self,
        workspace_id: UUID,
        checkpoint_db_id: UUID,
        changed_by: Optional[str] = None,
        changed_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Manually advance the active checkpoint pointer.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_db_id: UUID of the checkpoint to make active.
            changed_by: Optional identifier of who/what changed the pointer.
            changed_reason: Optional reason for the change.

        Returns:
            Dict with updated active checkpoint info.
        """
        active_pointer = self._checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_db_id,
            changed_by=changed_by,
            changed_reason=changed_reason,
        )

        # Get the checkpoint for audit
        checkpoint = self._checkpoint_repo.get_by_id(checkpoint_db_id)
        checkpoint_id = (
            checkpoint.checkpoint_id if checkpoint else str(checkpoint_db_id)
        )

        # Audit log
        self._audit_repo.create(
            category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
            action="active_pointer_changed",
            outcome="success",
            resource_type="checkpoint",
            resource_id=checkpoint_id,
            actor_id=changed_by,
            workspace_id=workspace_id,
            reason=changed_reason,
        )

        return {
            "workspace_id": str(workspace_id),
            "active_checkpoint_id": str(active_pointer.checkpoint_id),
            "changed_by": active_pointer.changed_by,
            "changed_reason": active_pointer.changed_reason,
            "updated_at": active_pointer.updated_at.isoformat()
            if active_pointer.updated_at
            else None,
        }

    def set_active_checkpoint_guarded(
        self,
        workspace_id: UUID,
        checkpoint_db_id: UUID,
        changed_by: Optional[str] = None,
        changed_reason: Optional[str] = None,
        is_operator: bool = True,  # Phase 3: operator-only by default
    ) -> dict[str, Any]:
        """Set active checkpoint with Phase 3 security guardrails.

        Phase 3 restrictions:
        - Only operators can manually change the pointer
        - Cannot rollback to older revisions (only advance to newest)
        - All changes are audited

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_db_id: UUID of the checkpoint to make active.
            changed_by: Optional identifier of who/what changed the pointer.
            changed_reason: Optional reason for the change.
            is_operator: Whether the requesting principal is an operator.

        Returns:
            Dict with updated active checkpoint info.

        Raises:
            PointerUpdateForbiddenError: If non-operator attempts update.
            PointerRollbackForbiddenError: If attempting to rollback to older revision.
        """
        # Phase 3: Operator-only check
        if not is_operator:
            # Audit the denied attempt
            target_checkpoint = self._checkpoint_repo.get_by_id(checkpoint_db_id)
            target_id = (
                target_checkpoint.checkpoint_id
                if target_checkpoint
                else str(checkpoint_db_id)
            )

            self._audit_repo.create(
                category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
                action="active_pointer_change_denied",
                outcome="denied",
                resource_type="checkpoint",
                resource_id=target_id,
                actor_id=changed_by,
                workspace_id=workspace_id,
                reason="Non-operator attempted pointer update",
            )

            raise PointerUpdateForbiddenError(
                "Only operators can manually change the active checkpoint pointer."
            )

        # Get the target checkpoint
        target_checkpoint = self._checkpoint_repo.get_by_id(checkpoint_db_id)
        if not target_checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_db_id} not found")

        # Phase 3: No rollback to older revisions
        # Get current active checkpoint
        current_active = self._checkpoint_repo.get_active_checkpoint(workspace_id)

        if current_active:
            # Compare creation times to prevent rollback
            # Only allow if target is newer than current (or same)
            if target_checkpoint.created_at < current_active.created_at:
                # This is a rollback attempt - forbidden in Phase 3
                self._audit_repo.create(
                    category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
                    action="active_pointer_rollback_denied",
                    outcome="denied",
                    resource_type="checkpoint",
                    resource_id=target_checkpoint.checkpoint_id,
                    actor_id=changed_by,
                    workspace_id=workspace_id,
                    reason=f"Rollback to older revision attempted: target={target_checkpoint.checkpoint_id}, current={current_active.checkpoint_id}",
                )

                raise PointerRollbackForbiddenError(
                    f"Cannot rollback to older checkpoint revision. "
                    f"Current: {current_active.checkpoint_id} (created {current_active.created_at}), "
                    f"Target: {target_checkpoint.checkpoint_id} (created {target_checkpoint.created_at}). "
                    "Phase 3 only supports advancing to newer checkpoints."
                )

        # All guardrails passed - perform the update
        active_pointer = self._checkpoint_repo.set_active_checkpoint(
            workspace_id=workspace_id,
            checkpoint_id=checkpoint_db_id,
            changed_by=changed_by,
            changed_reason=changed_reason,
        )

        # Audit the successful change
        self._audit_repo.create(
            category=AuditEventCategory.CHECKPOINT_MANAGEMENT,
            action="active_pointer_changed",
            outcome="success",
            resource_type="checkpoint",
            resource_id=target_checkpoint.checkpoint_id,
            actor_id=changed_by,
            workspace_id=workspace_id,
            reason=changed_reason,
        )

        return {
            "workspace_id": str(workspace_id),
            "active_checkpoint_id": str(active_pointer.checkpoint_id),
            "changed_by": active_pointer.changed_by,
            "changed_reason": active_pointer.changed_reason,
            "updated_at": active_pointer.updated_at.isoformat()
            if active_pointer.updated_at
            else None,
        }

    def get_active_checkpoint(
        self,
        workspace_id: UUID,
    ) -> Optional[dict[str, Any]]:
        """Get the currently active checkpoint for a workspace.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Dict with checkpoint info if set, None otherwise.
        """
        checkpoint = self._checkpoint_repo.get_active_checkpoint(workspace_id)
        if not checkpoint:
            return None

        return self._serialize_checkpoint(checkpoint)

    def get_checkpoint(
        self,
        checkpoint_db_id: UUID,
    ) -> Optional[dict[str, Any]]:
        """Get checkpoint by database ID.

        Args:
            checkpoint_db_id: UUID of the checkpoint record.

        Returns:
            Dict with checkpoint info if found, None otherwise.
        """
        checkpoint = self._checkpoint_repo.get_by_id(checkpoint_db_id)
        if not checkpoint:
            return None

        return self._serialize_checkpoint(checkpoint)

    def get_checkpoint_by_checkpoint_id(
        self,
        checkpoint_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get checkpoint by checkpoint_id string.

        Args:
            checkpoint_id: Unique checkpoint identifier.

        Returns:
            Dict with checkpoint info if found, None otherwise.
        """
        checkpoint = self._checkpoint_repo.get_by_checkpoint_id(checkpoint_id)
        if not checkpoint:
            return None

        return self._serialize_checkpoint(checkpoint)

    def list_checkpoints(
        self,
        workspace_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List checkpoints for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            limit: Maximum number of results.

        Returns:
            List of checkpoint info dicts.
        """
        checkpoints = self._checkpoint_repo.list_by_workspace(
            workspace_id=workspace_id, limit=limit
        )
        return [self._serialize_checkpoint(c) for c in checkpoints]

    def _get_storage_key(self, workspace_id: UUID, checkpoint_id: UUID) -> str:
        """Generate storage key for checkpoint.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: UUID of the checkpoint.

        Returns:
            Storage key string.
        """
        return f"workspaces/{workspace_id}/checkpoints/{checkpoint_id}"

    def _serialize_manifest(self, manifest: CheckpointManifest) -> str:
        """Serialize checkpoint manifest to JSON string.

        Args:
            manifest: CheckpointManifest instance.

        Returns:
            JSON string representation.
        """
        import json

        return json.dumps(manifest.to_dict())

    def _serialize_checkpoint(self, checkpoint: Any) -> dict[str, Any]:
        """Serialize a WorkspaceCheckpoint to a dict.

        Args:
            checkpoint: WorkspaceCheckpoint model instance.

        Returns:
            Dict representation of the checkpoint.
        """
        # Handle both enum (PostgreSQL) and string (SQLite) states
        state = checkpoint.state
        if hasattr(state, "value"):
            state = state.value

        return {
            "id": str(checkpoint.id),
            "workspace_id": str(checkpoint.workspace_id),
            "checkpoint_id": checkpoint.checkpoint_id,
            "version": checkpoint.version,
            "state": state,
            "storage_key": checkpoint.storage_key,
            "storage_size_bytes": checkpoint.storage_size_bytes,
            "manifest": checkpoint.manifest_json,
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
