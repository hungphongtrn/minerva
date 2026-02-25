"""Sandbox orchestrator service for health-aware routing and lifecycle management.

Provides service-level orchestration for sandbox selection, provisioning,
and idle TTL enforcement with health-aware routing decisions.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.config.settings import settings
from src.db.models import (
    AgentPack,
    AgentPackValidationStatus,
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
)
from src.db.repositories.agent_pack_repository import AgentPackRepository
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository
from src.infrastructure.sandbox.providers.base import (
    SandboxProvider,
    SandboxConfig,
    SandboxInfo,
    SandboxState as ProviderSandboxState,
    SandboxHealth as ProviderSandboxHealth,
    SandboxNotFoundError,
    SandboxProviderError,
)
from src.infrastructure.sandbox.providers.factory import get_provider


class RoutingResult(Enum):
    """Result codes for sandbox routing operations."""

    ROUTED_EXISTING = auto()  # Successfully routed to existing sandbox
    PROVISIONED_NEW = auto()  # Provisioned new sandbox
    HYDRATED_EXISTING = auto()  # Hydrated/reactivated existing sandbox
    UNHEALTHY_EXCLUDED = auto()  # Unhealthy sandbox excluded from routing
    NO_HEALTHY_CANDIDATES = auto()  # No healthy sandboxes available
    PROVISION_FAILED = auto()  # Failed to provision new sandbox


@dataclass
class SandboxRoutingResult:
    """Result of a sandbox routing attempt."""

    success: bool
    result: RoutingResult
    sandbox: Optional[SandboxInstance]
    provider_info: Optional[SandboxInfo]
    message: str
    excluded_unhealthy: List[SandboxInstance]


@dataclass
class StopEligibilityResult:
    """Result of stop eligibility check."""

    eligible: bool
    reason: str
    idle_seconds: Optional[int]
    ttl_seconds: int


class SandboxOrchestratorService:
    """Service for sandbox lifecycle orchestration and routing.

    This service provides the control-plane layer for:
    - Health-aware sandbox selection (prefer active healthy)
    - Unhealthy sandbox exclusion and replacement
    - Configurable idle TTL enforcement
    - Idempotent stop operations

    The service is fail-closed: unhealthy sandboxes are excluded from
    routing, and ambiguous states default to provisioning new sandboxes.
    """

    # Default idle TTL from settings, fallback to 1 hour
    DEFAULT_IDLE_TTL_SECONDS = 3600

    # Minimum allowed TTL: 60 seconds
    MIN_IDLE_TTL_SECONDS = 60

    # Maximum allowed TTL: 24 hours
    MAX_IDLE_TTL_SECONDS = 86400

    def __init__(
        self,
        session: Session,
        provider: Optional[SandboxProvider] = None,
        idle_ttl_seconds: Optional[int] = None,
    ):
        """Initialize the orchestrator service.

        Args:
            session: SQLAlchemy session for database operations.
            provider: Sandbox provider instance (defaults to configured profile).
            idle_ttl_seconds: Idle TTL in seconds (defaults to settings or 1 hour).
        """
        self._session = session
        self._repository = SandboxInstanceRepository(session)
        self._provider = provider or get_provider()
        self._idle_ttl_seconds = self._validate_ttl(
            idle_ttl_seconds or self._get_configured_ttl()
        )

    def _get_configured_ttl(self) -> int:
        """Get TTL from settings or use default.

        Returns:
            Configured TTL in seconds.
        """
        # Check for settings attribute first
        ttl = getattr(settings, "SANDBOX_IDLE_TTL_SECONDS", None)
        if ttl is not None:
            return int(ttl)
        return self.DEFAULT_IDLE_TTL_SECONDS

    def _validate_ttl(self, ttl_seconds: int) -> int:
        """Validate TTL value.

        Args:
            ttl_seconds: TTL value to validate.

        Returns:
            Validated TTL.

        Raises:
            ValueError: If TTL is outside allowed range.
        """
        if ttl_seconds < self.MIN_IDLE_TTL_SECONDS:
            raise ValueError(
                f"Idle TTL must be at least {self.MIN_IDLE_TTL_SECONDS} seconds, "
                f"got {ttl_seconds}"
            )
        if ttl_seconds > self.MAX_IDLE_TTL_SECONDS:
            raise ValueError(
                f"Idle TTL must be at most {self.MAX_IDLE_TTL_SECONDS} seconds, "
                f"got {ttl_seconds}"
            )
        return ttl_seconds

    async def resolve_sandbox(
        self,
        workspace_id: UUID,
        profile: Optional[SandboxProfile] = None,
        agent_pack_id: Optional[UUID] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> SandboxRoutingResult:
        """Resolve a sandbox for workspace execution.

        Routing logic:
        1. List candidate sandboxes for workspace (filtered by profile if provided)
        2. Filter to ACTIVE state
        3. Check health of each candidate
        4. Route to first healthy candidate
        5. If none healthy, mark unhealthy as excluded and provision replacement

        Args:
            workspace_id: UUID of the workspace.
            profile: Optional deployment profile filter.
            agent_pack_id: Optional agent pack to attach.
            env_vars: Optional environment variables for new sandboxes.

        Returns:
            SandboxRoutingResult with routing outcome.
        """
        excluded_unhealthy: List[SandboxInstance] = []

        try:
            # Step 1: Get active sandboxes for workspace
            active_sandboxes = self._repository.list_active_healthy_by_workspace(
                workspace_id=workspace_id,
                profile=profile,
            )

            # Step 2: Check health of each candidate
            for sandbox in active_sandboxes:
                health_result = await self._check_sandbox_health(sandbox)

                if (
                    health_result
                    and health_result.health == ProviderSandboxHealth.HEALTHY
                ):
                    # Update activity timestamp
                    self._repository.update_activity(sandbox.id)

                    return SandboxRoutingResult(
                        success=True,
                        result=RoutingResult.ROUTED_EXISTING,
                        sandbox=sandbox,
                        provider_info=health_result,
                        message=f"Routed to healthy sandbox {sandbox.id}",
                        excluded_unhealthy=excluded_unhealthy,
                    )
                else:
                    # Mark as unhealthy and exclude
                    self._mark_unhealthy(sandbox)
                    excluded_unhealthy.append(sandbox)

            # Step 3: No healthy candidates - need to provision
            return await self._provision_sandbox(
                workspace_id=workspace_id,
                profile=profile,
                agent_pack_id=agent_pack_id,
                env_vars=env_vars,
                excluded_unhealthy=excluded_unhealthy,
            )

        except Exception as e:
            return SandboxRoutingResult(
                success=False,
                result=RoutingResult.NO_HEALTHY_CANDIDATES,
                sandbox=None,
                provider_info=None,
                message=f"Sandbox resolution failed: {str(e)}",
                excluded_unhealthy=excluded_unhealthy,
            )

    async def _check_sandbox_health(
        self, sandbox: SandboxInstance
    ) -> Optional[SandboxInfo]:
        """Check health of a sandbox via provider.

        Args:
            sandbox: Sandbox instance to check.

        Returns:
            SandboxInfo if health check succeeds, None otherwise.
        """
        if not sandbox.provider_ref:
            return None

        try:
            from src.infrastructure.sandbox.providers.base import SandboxRef

            ref = SandboxRef(
                provider_ref=sandbox.provider_ref,
                profile=sandbox.profile,
            )
            return await self._provider.get_health(ref)
        except (SandboxNotFoundError, SandboxProviderError):
            return None

    def _mark_unhealthy(self, sandbox: SandboxInstance) -> None:
        """Mark a sandbox as unhealthy in the database.

        Args:
            sandbox: Sandbox to mark.
        """
        self._repository.update_health(sandbox.id, SandboxHealthStatus.UNHEALTHY)
        self._repository.update_state(sandbox.id, SandboxState.UNHEALTHY)

    async def _provision_sandbox(
        self,
        workspace_id: UUID,
        profile: Optional[SandboxProfile],
        agent_pack_id: Optional[UUID],
        env_vars: Optional[Dict[str, str]],
        excluded_unhealthy: List[SandboxInstance],
    ) -> SandboxRoutingResult:
        """Provision a new sandbox.

        Args:
            workspace_id: Workspace to provision for.
            profile: Deployment profile.
            agent_pack_id: Agent pack to attach.
            env_vars: Environment variables.
            excluded_unhealthy: List of excluded unhealthy sandboxes.

        Returns:
            SandboxRoutingResult with provisioning outcome.
        """
        pack_source_path: Optional[str] = None

        # Resolve and validate agent pack if provided (fail-closed)
        if agent_pack_id:
            pack_repo = AgentPackRepository(self._session)
            pack = pack_repo.get_by_id(agent_pack_id)

            # Validation: pack must exist
            if not pack:
                return SandboxRoutingResult(
                    success=False,
                    result=RoutingResult.PROVISION_FAILED,
                    sandbox=None,
                    provider_info=None,
                    message=f"Agent pack not found: {agent_pack_id}",
                    excluded_unhealthy=excluded_unhealthy,
                )

            # Validation: pack must belong to the workspace
            if pack.workspace_id != workspace_id:
                return SandboxRoutingResult(
                    success=False,
                    result=RoutingResult.PROVISION_FAILED,
                    sandbox=None,
                    provider_info=None,
                    message=f"Agent pack {agent_pack_id} does not belong to workspace {workspace_id}",
                    excluded_unhealthy=excluded_unhealthy,
                )

            # Validation: pack must be active
            if not pack.is_active:
                return SandboxRoutingResult(
                    success=False,
                    result=RoutingResult.PROVISION_FAILED,
                    sandbox=None,
                    provider_info=None,
                    message=f"Agent pack {agent_pack_id} is not active",
                    excluded_unhealthy=excluded_unhealthy,
                )

            # Validation: pack must be valid (not pending, invalid, or stale)
            if pack.validation_status != AgentPackValidationStatus.VALID:
                return SandboxRoutingResult(
                    success=False,
                    result=RoutingResult.PROVISION_FAILED,
                    sandbox=None,
                    provider_info=None,
                    message=f"Agent pack {agent_pack_id} is not valid (status: {pack.validation_status.value})",
                    excluded_unhealthy=excluded_unhealthy,
                )

            pack_source_path = pack.source_path

        try:
            # Create database record first
            sandbox = self._repository.create(
                workspace_id=workspace_id,
                profile=profile or SandboxProfile.LOCAL_COMPOSE,
                agent_pack_id=agent_pack_id,
                idle_ttl_seconds=self._idle_ttl_seconds,
            )

            # Update state to CREATING
            self._repository.update_state(sandbox.id, SandboxState.CREATING)

            # Provision via provider with pack source path
            config = SandboxConfig(
                workspace_id=workspace_id,
                idle_ttl_seconds=self._idle_ttl_seconds,
                env_vars=env_vars or {},
                pack_source_path=pack_source_path,
            )

            provider_info = await self._provider.provision_sandbox(config)

            # Update record with provider reference
            if provider_info and provider_info.ref:
                self._repository.set_provider_ref(
                    sandbox.id, provider_info.ref.provider_ref
                )
                self._repository.update_state(sandbox.id, SandboxState.ACTIVE)
                self._repository.update_health(sandbox.id, SandboxHealthStatus.HEALTHY)
                self._repository.update_activity(sandbox.id)

            return SandboxRoutingResult(
                success=True,
                result=RoutingResult.PROVISIONED_NEW,
                sandbox=sandbox,
                provider_info=provider_info,
                message=f"Provisioned new sandbox {sandbox.id}",
                excluded_unhealthy=excluded_unhealthy,
            )

        except Exception as e:
            return SandboxRoutingResult(
                success=False,
                result=RoutingResult.PROVISION_FAILED,
                sandbox=None,
                provider_info=None,
                message=f"Failed to provision sandbox: {str(e)}",
                excluded_unhealthy=excluded_unhealthy,
            )

    def check_stop_eligibility(self, sandbox: SandboxInstance) -> StopEligibilityResult:
        """Check if a sandbox is eligible for idle stop.

        Uses the configured idle TTL to determine eligibility.

        Args:
            sandbox: Sandbox to check.

        Returns:
            StopEligibilityResult with eligibility determination.
        """
        # Only active sandboxes can be stopped
        if sandbox.state != SandboxState.ACTIVE:
            return StopEligibilityResult(
                eligible=False,
                reason=f"Sandbox is not active (state: {sandbox.state})",
                idle_seconds=None,
                ttl_seconds=self._idle_ttl_seconds,
            )

        # Need last activity timestamp
        if not sandbox.last_activity_at:
            # If no activity recorded, use created_at
            last_activity = sandbox.created_at
        else:
            last_activity = sandbox.last_activity_at

        now = datetime.utcnow()
        idle_duration = (now - last_activity).total_seconds()

        # Use sandbox-specific TTL if set, otherwise use configured TTL
        ttl = sandbox.idle_ttl_seconds or self._idle_ttl_seconds

        if idle_duration >= ttl:
            return StopEligibilityResult(
                eligible=True,
                reason=f"Sandbox idle for {int(idle_duration)}s (TTL: {ttl}s)",
                idle_seconds=int(idle_duration),
                ttl_seconds=ttl,
            )

        return StopEligibilityResult(
            eligible=False,
            reason=f"Sandbox active within TTL window (idle: {int(idle_duration)}s, TTL: {ttl}s)",
            idle_seconds=int(idle_duration),
            ttl_seconds=ttl,
        )

    async def stop_idle_sandboxes(
        self, workspace_id: Optional[UUID] = None
    ) -> List[SandboxInstance]:
        """Stop sandboxes that have exceeded idle TTL.

        Args:
            workspace_id: Optional workspace to limit scope.

        Returns:
            List of sandboxes that were stopped.
        """
        stopped = []

        # Get all active sandboxes
        if workspace_id:
            candidates = self._repository.list_by_workspace(
                workspace_id=workspace_id, include_inactive=False
            )
        else:
            # Get all sandboxes and filter to active
            # Note: This could be optimized with a dedicated query
            candidates = []

        # Filter to those eligible for stop
        for sandbox in candidates:
            eligibility = self.check_stop_eligibility(sandbox)
            if eligibility.eligible:
                stopped_sandbox = await self._stop_sandbox(sandbox)
                if stopped_sandbox:
                    stopped.append(stopped_sandbox)

        return stopped

    async def _stop_sandbox(
        self, sandbox: SandboxInstance
    ) -> Optional[SandboxInstance]:
        """Stop a sandbox (idempotent).

        Args:
            sandbox: Sandbox to stop.

        Returns:
            Stopped sandbox instance if successful.
        """
        try:
            # Update state to STOPPING
            self._repository.update_state(sandbox.id, SandboxState.STOPPING)

            # Call provider stop if we have a provider ref
            if sandbox.provider_ref:
                try:
                    from src.infrastructure.sandbox.providers.base import SandboxRef

                    ref = SandboxRef(
                        provider_ref=sandbox.provider_ref,
                        profile=sandbox.profile,
                    )
                    await self._provider.stop_sandbox(ref)
                except SandboxNotFoundError:
                    # Already stopped/not found - idempotent
                    pass

            # Update to STOPPED
            stopped = self._repository.update_state(sandbox.id, SandboxState.STOPPED)
            return stopped

        except Exception:
            # Mark as failed but don't raise
            self._repository.update_state(sandbox.id, SandboxState.FAILED)
            return None

    def list_idle_sandboxes(
        self, workspace_id: Optional[UUID] = None
    ) -> List[SandboxInstance]:
        """List sandboxes eligible for idle stop.

        Args:
            workspace_id: Optional workspace filter.

        Returns:
            List of idle sandboxes.
        """
        # Get candidates
        if workspace_id:
            candidates = self._repository.list_by_workspace(
                workspace_id=workspace_id, include_inactive=False
            )
        else:
            # Would need a broader query - for now return empty
            return []

        # Filter to eligible
        idle = []
        for sandbox in candidates:
            eligibility = self.check_stop_eligibility(sandbox)
            if eligibility.eligible:
                idle.append(sandbox)

        return idle

    async def get_sandbox_health(self, sandbox_id: UUID) -> Optional[SandboxInfo]:
        """Get current health for a sandbox.

        Args:
            sandbox_id: UUID of the sandbox.

        Returns:
            SandboxInfo with current health, or None if not found.
        """
        sandbox = self._repository.get_by_id(sandbox_id)
        if not sandbox:
            return None

        return await self._check_sandbox_health(sandbox)

    def update_sandbox_activity(self, sandbox_id: UUID) -> Optional[SandboxInstance]:
        """Update last activity timestamp for a sandbox.

        Args:
            sandbox_id: UUID of the sandbox.

        Returns:
            Updated sandbox instance.
        """
        return self._repository.update_activity(sandbox_id)
