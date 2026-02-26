"""Workspace lifecycle service for durable workspace continuity.

Provides high-level lifecycle orchestration ensuring:
- Durable workspace existence per user (auto-create on first use, reuse thereafter)
- Lease acquisition for write path serialization
- Sandbox resolution with health-aware routing
- Deterministic lease release in all success/failure branches
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.db.models import Workspace, User, SandboxState, SandboxHealthStatus
from src.db.repositories.workspace_lease_repository import WorkspaceLeaseRepository
from src.services.workspace_lease_service import (
    WorkspaceLeaseService,
    LeaseAcquisitionResult,
    LeaseReleaseResult,
    LeaseResult,
)
from src.services.sandbox_orchestrator_service import (
    SandboxOrchestratorService,
    SandboxRoutingResult,
)
from src.infrastructure.sandbox.providers.factory import get_provider


@dataclass
class LifecycleTarget:
    """Result of workspace lifecycle resolution.

    Contains workspace, lease status, and routing target information.
    """

    workspace: Workspace
    lease_acquired: bool
    lease_result: Optional[LeaseAcquisitionResult]
    sandbox: Optional[Any]  # SandboxInstance
    routing_result: Optional[SandboxRoutingResult]
    error: Optional[str] = None
    # Restore-aware fields
    restore_state: Optional[str] = None  # "none", "in_progress", "completed", "failed"
    restore_checkpoint_id: Optional[str] = None  # ID of checkpoint being restored
    queued: bool = False  # True if run is queued due to restore in progress


@dataclass
class LifecycleContext:
    """Context for a lifecycle operation with automatic cleanup."""

    workspace_id: UUID
    run_id: str
    lease_service: WorkspaceLeaseService
    acquired_lease: bool = False
    released: bool = False

    def release(self) -> LeaseReleaseResult:
        """Release the lease if acquired."""
        if self.acquired_lease and not self.released:
            result = self.lease_service.release_lease(
                workspace_id=self.workspace_id,
                holder_run_id=self.run_id,
            )
            self.released = True
            return result
        return LeaseReleaseResult(
            success=True,
            result=LeaseResult.RELEASED,
            released_at=None,
            message="Lease already released or not acquired",
        )


class WorkspaceLifecycleService:
    """Service for workspace lifecycle orchestration.

    This is the primary entrypoint for workspace operations, ensuring:
    1. Durable workspace existence per authenticated user
    2. Write path serialization via lease acquisition
    3. Health-aware sandbox routing with idle TTL enforcement
    4. Deterministic lease cleanup in all branches
    5. Cold-start restore coordination to prevent duplicate restores

    Usage:
        lifecycle = WorkspaceLifecycleService(session)
        target = await lifecycle.resolve_target(
            principal=current_user,
            auto_create=True,
        )

        if target.lease_acquired:
            try:
                # Use target.sandbox for execution
                pass
            finally:
                lifecycle.release_lease(target.workspace.id, run_id)
    """

    DEFAULT_LEASE_TTL_SECONDS = 300  # 5 minutes

    # Class-level tracking for restore-in-progress to prevent duplicate restores
    # Format: {workspace_id_str: {"started_at": datetime, "checkpoint_id": str}}
    _restore_in_progress: Dict[str, Any] = {}

    def __init__(
        self,
        session: Session,
        lease_service: Optional[WorkspaceLeaseService] = None,
        orchestrator: Optional[SandboxOrchestratorService] = None,
    ):
        """Initialize the lifecycle service.

        Args:
            session: SQLAlchemy session for database operations.
            lease_service: Optional lease service instance.
            orchestrator: Optional orchestrator service instance.
        """
        self._session = session
        self._lease_service = lease_service or WorkspaceLeaseService(session)
        self._orchestrator = orchestrator

    async def resolve_target(
        self,
        principal: Any,
        auto_create: bool = True,
        acquire_lease: bool = True,
        run_id: Optional[str] = None,
        lease_ttl_seconds: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        workspace: Optional[Workspace] = None,
        agent_pack_id: Optional[str] = None,
    ) -> LifecycleTarget:
        """Resolve workspace and routing target for a principal.

        This is the primary entrypoint for workspace operations. It:
        1. Ensures workspace exists for the principal (auto-creates if needed)
        2. Acquires lease if requested
        3. Resolves sandbox target via orchestrator
        4. Returns complete target information

        Args:
            principal: Authenticated principal (User or similar).
            auto_create: If True, create workspace if it doesn't exist.
            acquire_lease: If True, acquire write lease for the workspace.
            run_id: Optional run identifier for lease tracking.
            lease_ttl_seconds: Lease TTL override (default: 5 minutes).
            env_vars: Optional environment variables for sandbox provisioning.
            workspace: Optional specific workspace to use (bypasses lookup).
            agent_pack_id: Optional agent pack ID to bind to the sandbox.

        Returns:
            LifecycleTarget with workspace, lease status, and routing info.
        """
        generated_run_id = run_id or str(uuid4())
        lease_ttl = lease_ttl_seconds or self.DEFAULT_LEASE_TTL_SECONDS

        try:
            # Step 1: Resolve or create workspace (if not provided)
            if workspace is None:
                workspace = self._resolve_workspace(principal, auto_create=auto_create)
            if not workspace:
                return LifecycleTarget(
                    workspace=None,  # type: ignore
                    lease_acquired=False,
                    lease_result=None,
                    sandbox=None,
                    routing_result=None,
                    error="Workspace not found and auto_create is disabled",
                )

            # Step 2: Acquire lease if requested
            lease_result = None
            lease_acquired = False

            if acquire_lease:
                lease_result = self._lease_service.acquire_lease(
                    workspace_id=workspace.id,
                    holder_run_id=generated_run_id,
                    holder_identity=str(getattr(principal, "id", str(principal))),
                    ttl_seconds=lease_ttl,
                )
                lease_acquired = lease_result.success

                if not lease_acquired:
                    # Lease acquisition failed - return early with conflict info
                    return LifecycleTarget(
                        workspace=workspace,
                        lease_acquired=False,
                        lease_result=lease_result,
                        sandbox=None,
                        routing_result=None,
                        error=lease_result.message
                        if lease_result
                        else "Lease acquisition failed",
                    )

            # Step 3: Resolve sandbox target (with optional agent pack binding)
            routing_result = await self._resolve_sandbox(
                workspace=workspace,
                run_id=generated_run_id,
                env_vars=env_vars,
                agent_pack_id=agent_pack_id,
            )

            return LifecycleTarget(
                workspace=workspace,
                lease_acquired=lease_acquired,
                lease_result=lease_result,
                sandbox=routing_result.sandbox if routing_result else None,
                routing_result=routing_result,
                error=None
                if (routing_result and routing_result.success)
                else (routing_result.message if routing_result else "Routing failed"),
            )

        except Exception as e:
            return LifecycleTarget(
                workspace=None,  # type: ignore
                lease_acquired=False,
                lease_result=None,
                sandbox=None,
                routing_result=None,
                error=f"Lifecycle resolution failed: {str(e)}",
            )

    def _resolve_workspace(
        self,
        principal: Any,
        auto_create: bool = True,
    ) -> Optional[Workspace]:
        """Resolve workspace for principal.

        For v1: One durable workspace per user. Returns the user's workspace
        or auto-creates if not found.

        Args:
            principal: Authenticated principal.
            auto_create: If True, create workspace if needed.

        Returns:
            Workspace instance or None if not found and auto_create is False.
        """
        from uuid import UUID

        # Get user ID from principal - try both 'id' and 'user_id' attributes
        user_id_raw = getattr(principal, "user_id", None) or getattr(
            principal, "id", None
        )
        if not user_id_raw:
            return None

        # Convert to UUID if needed
        if isinstance(user_id_raw, str):
            try:
                user_id = UUID(user_id_raw)
            except ValueError:
                return None
        else:
            user_id = user_id_raw

        # Look for existing workspace owned by user
        workspace = (
            self._session.query(Workspace).filter(Workspace.owner_id == user_id).first()
        )

        if workspace:
            return workspace

        # Auto-create if enabled
        if auto_create:
            return self._create_workspace_for_user(principal)

        return None

    def _create_workspace_for_user(self, user: Any) -> Workspace:
        """Create a new workspace for a user.

        Args:
            user: User to create workspace for.

        Returns:
            Created workspace.
        """
        from uuid import UUID

        user_id_raw = getattr(user, "user_id", None) or getattr(user, "id", None)

        # Convert to UUID if needed
        if isinstance(user_id_raw, str):
            try:
                user_id = UUID(user_id_raw)
            except ValueError:
                user_id = uuid4()
        elif user_id_raw is None:
            user_id = uuid4()
        else:
            user_id = user_id_raw

        user_email = getattr(user, "email", f"user_{user_id}@example.com")

        workspace = Workspace(
            id=uuid4(),
            name=f"Workspace for {user_email}",
            slug=f"workspace-{user_id}-{uuid4().hex[:8]}",
            owner_id=user_id,
            is_active=True,
        )

        self._session.add(workspace)
        self._session.commit()

        return workspace

    async def _resolve_sandbox(
        self,
        workspace: Workspace,
        run_id: str,
        env_vars: Optional[Dict[str, str]] = None,
        agent_pack_id: Optional[str] = None,
    ) -> Optional[SandboxRoutingResult]:
        """Resolve sandbox target for workspace.

        Args:
            workspace: Workspace to resolve sandbox for.
            run_id: Run identifier for tracking.
            env_vars: Optional environment variables.
            agent_pack_id: Optional agent pack ID to bind to the sandbox.

        Returns:
            SandboxRoutingResult or None if resolution fails.
        """
        if not self._orchestrator:
            # Initialize orchestrator lazily with default provider
            self._orchestrator = SandboxOrchestratorService(
                session=self._session,
                provider=get_provider(),
            )

        try:
            # Convert agent_pack_id string to UUID if provided
            pack_id_uuid: Optional[UUID] = None
            if agent_pack_id:
                try:
                    pack_id_uuid = UUID(agent_pack_id)
                except ValueError:
                    return SandboxRoutingResult(
                        success=False,
                        result=None,  # type: ignore
                        sandbox=None,
                        provider_info=None,
                        message=f"Invalid agent_pack_id format: {agent_pack_id}",
                        excluded_unhealthy=[],
                    )

            result = await self._orchestrator.resolve_sandbox(
                workspace_id=workspace.id,
                env_vars=env_vars,
                agent_pack_id=pack_id_uuid,
            )
            return result
        except Exception as e:
            # Return failed result
            return SandboxRoutingResult(
                success=False,
                result=None,  # type: ignore
                sandbox=None,
                provider_info=None,
                message=f"Sandbox resolution failed: {str(e)}",
                excluded_unhealthy=[],
            )

    def release_lease(
        self,
        workspace_id: UUID,
        run_id: str,
        require_holder_match: bool = True,
    ) -> LeaseReleaseResult:
        """Release a workspace lease.

        This should be called in finally blocks to ensure deterministic
        lease release regardless of success or failure.

        Args:
            workspace_id: UUID of the workspace.
            run_id: Run ID that holds the lease.
            require_holder_match: If True, verify holder matches.

        Returns:
            LeaseReleaseResult with release status.
        """
        return self._lease_service.release_lease(
            workspace_id=workspace_id,
            holder_run_id=run_id,
            require_holder_match=require_holder_match,
        )

    async def ensure_workspace(
        self,
        principal: Any,
    ) -> Optional[Workspace]:
        """Ensure workspace exists for principal (public API).

        Args:
            principal: Authenticated principal.

        Returns:
            Workspace or None if not found.
        """
        return self._resolve_workspace(principal, auto_create=True)

    def get_workspace(self, workspace_id: UUID) -> Optional[Workspace]:
        """Get workspace by ID.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Workspace or None if not found.
        """
        return (
            self._session.query(Workspace).filter(Workspace.id == workspace_id).first()
        )

    async def get_or_create_workspace(
        self,
        principal: Any,
    ) -> Workspace:
        """Get existing workspace or create new one.

        This is a convenience method for simple workspace resolution
        without lease or sandbox routing.

        Args:
            principal: Authenticated principal.

        Returns:
            Workspace instance.
        """
        workspace = self._resolve_workspace(principal, auto_create=True)
        if not workspace:
            raise RuntimeError(f"Failed to resolve workspace for principal {principal}")
        return workspace

    # Restore coordination methods

    def is_restore_in_progress(self, workspace_id: UUID) -> bool:
        """Check if a restore is currently in progress for a workspace.

        Uses class-level tracking to prevent duplicate cold-start restores.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            True if restore is in progress, False otherwise.
        """
        workspace_id_str = str(workspace_id)
        if workspace_id_str not in self._restore_in_progress:
            return False

        # Check if restore has timed out (5 minutes max)
        restore_info = self._restore_in_progress[workspace_id_str]
        started_at = restore_info.get("started_at")
        if started_at:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed > 300:  # 5 minute timeout
                # Clean up stale restore entry
                del self._restore_in_progress[workspace_id_str]
                return False

        return True

    def get_restore_checkpoint_id(self, workspace_id: UUID) -> Optional[str]:
        """Get the checkpoint ID being restored for a workspace.

        Args:
            workspace_id: UUID of the workspace.

        Returns:
            Checkpoint ID string if restore in progress, None otherwise.
        """
        workspace_id_str = str(workspace_id)
        if workspace_id_str in self._restore_in_progress:
            return self._restore_in_progress[workspace_id_str].get("checkpoint_id")
        return None

    def mark_restore_started(
        self,
        workspace_id: UUID,
        checkpoint_id: str,
    ) -> None:
        """Mark that a restore has started for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            checkpoint_id: ID of the checkpoint being restored.
        """
        workspace_id_str = str(workspace_id)
        self._restore_in_progress[workspace_id_str] = {
            "started_at": datetime.now(timezone.utc),
            "checkpoint_id": checkpoint_id,
        }

    def mark_restore_completed(self, workspace_id: UUID) -> None:
        """Mark that a restore has completed for a workspace.

        Args:
            workspace_id: UUID of the workspace.
        """
        workspace_id_str = str(workspace_id)
        if workspace_id_str in self._restore_in_progress:
            del self._restore_in_progress[workspace_id_str]

    def mark_restore_failed(self, workspace_id: UUID) -> None:
        """Mark that a restore has failed for a workspace.

        Args:
            workspace_id: UUID of the workspace.
        """
        workspace_id_str = str(workspace_id)
        if workspace_id_str in self._restore_in_progress:
            del self._restore_in_progress[workspace_id_str]
