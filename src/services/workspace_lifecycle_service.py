"""Workspace lifecycle service for durable workspace continuity.

Provides high-level lifecycle orchestration ensuring:
- Durable workspace existence per user (auto-create on first use, reuse thereafter)
- Lease acquisition for write path serialization
- Sandbox resolution with health-aware routing
- Deterministic lease release in all success/failure branches
"""

from dataclasses import dataclass
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

        Returns:
            LifecycleTarget with workspace, lease status, and routing info.
        """
        generated_run_id = run_id or str(uuid4())
        lease_ttl = lease_ttl_seconds or self.DEFAULT_LEASE_TTL_SECONDS

        try:
            # Step 1: Resolve or create workspace
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

            # Step 3: Resolve sandbox target
            routing_result = await self._resolve_sandbox(
                workspace=workspace,
                run_id=generated_run_id,
                env_vars=env_vars,
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
        # Get user ID from principal
        user_id = getattr(principal, "id", None)
        if not user_id:
            return None

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
        user_id = getattr(user, "id", uuid4())
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
    ) -> Optional[SandboxRoutingResult]:
        """Resolve sandbox target for workspace.

        Args:
            workspace: Workspace to resolve sandbox for.
            run_id: Run identifier for tracking.
            env_vars: Optional environment variables.

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
            result = await self._orchestrator.resolve_sandbox(
                workspace_id=workspace.id,
                env_vars=env_vars,
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
