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
    ttl_cleanup_applied: bool = False
    stopped_sandbox_ids: List[str] = None
    ttl_cleanup_reason: Optional[str] = None

    def __post_init__(self):
        if self.stopped_sandbox_ids is None:
            self.stopped_sandbox_ids = []


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
        1. Stop idle sandboxes that exceeded TTL (TTL cleanup enforcement)
        2. List candidate sandboxes for workspace (filtered by profile if provided)
        3. Filter to ACTIVE state
        4. Check health of each candidate
        5. Route to first healthy candidate
        6. If none healthy, mark unhealthy as excluded and provision replacement

        Args:
            workspace_id: UUID of the workspace.
            profile: Optional deployment profile filter.
            agent_pack_id: Optional agent pack to attach.
            env_vars: Optional environment variables for new sandboxes.

        Returns:
            SandboxRoutingResult with routing outcome.
        """
        excluded_unhealthy: List[SandboxInstance] = []
        ttl_cleanup_applied = False
        stopped_sandbox_ids: List[str] = []
        ttl_cleanup_reason: Optional[str] = None

        try:
            # Step 1: Stop idle sandboxes that exceeded TTL
            stopped_idle = await self._stop_idle_sandboxes_before_routing(workspace_id)
            if stopped_idle:
                ttl_cleanup_applied = True
                stopped_sandbox_ids = [str(s.id) for s in stopped_idle]
                ttl_cleanup_reason = (
                    f"Stopped {len(stopped_idle)} idle sandbox(s) "
                    f"exceeding TTL ({self._idle_ttl_seconds}s)"
                )

            # Step 2: Get active sandboxes for workspace
            active_sandboxes = self._repository.list_active_healthy_by_workspace(
                workspace_id=workspace_id,
                profile=profile,
            )

            # Step 3: Check health of each candidate
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
                        ttl_cleanup_applied=ttl_cleanup_applied,
                        stopped_sandbox_ids=stopped_sandbox_ids,
                        ttl_cleanup_reason=ttl_cleanup_reason,
                    )
                else:
                    # Mark as unhealthy and exclude
                    self._mark_unhealthy(sandbox)
                    excluded_unhealthy.append(sandbox)

            # Step 4: No healthy candidates - need to provision
            return await self._provision_sandbox(
                workspace_id=workspace_id,
                profile=profile,
                agent_pack_id=agent_pack_id,
                env_vars=env_vars,
                excluded_unhealthy=excluded_unhealthy,
                ttl_cleanup_applied=ttl_cleanup_applied,
                stopped_sandbox_ids=stopped_sandbox_ids,
                ttl_cleanup_reason=ttl_cleanup_reason,
            )

        except Exception as e:
            return SandboxRoutingResult(
                success=False,
                result=RoutingResult.NO_HEALTHY_CANDIDATES,
                sandbox=None,
                provider_info=None,
                message=f"Sandbox resolution failed: {str(e)}",
                excluded_unhealthy=excluded_unhealthy,
                ttl_cleanup_applied=ttl_cleanup_applied,
                stopped_sandbox_ids=stopped_sandbox_ids,
                ttl_cleanup_reason=ttl_cleanup_reason,
            )

    async def _stop_idle_sandboxes_before_routing(
        self, workspace_id: UUID
    ) -> List[SandboxInstance]:
        """Stop idle sandboxes before routing resolution.

        This enforces TTL policy by stopping any sandboxes that have
        exceeded their idle TTL before routing decisions are made.

        Args:
            workspace_id: Workspace to check for idle sandboxes.

        Returns:
            List of sandboxes that were stopped.
        """
        stopped: List[SandboxInstance] = []

        # Get all active sandboxes for the workspace
        candidates = self._repository.list_by_workspace(
            workspace_id=workspace_id, include_inactive=False
        )

        # Filter to those eligible for stop (exceeded TTL)
        for sandbox in candidates:
            eligibility = self.check_stop_eligibility(sandbox)
            if eligibility.eligible:
                stopped_sandbox = await self._stop_sandbox(sandbox)
                if stopped_sandbox:
                    stopped.append(stopped_sandbox)

        return stopped

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
        ttl_cleanup_applied: bool = False,
        stopped_sandbox_ids: Optional[List[str]] = None,
        ttl_cleanup_reason: Optional[str] = None,
    ) -> SandboxRoutingResult:
        """Provision a new sandbox.

        Args:
            workspace_id: Workspace to provision for.
            profile: Deployment profile.
            agent_pack_id: Agent pack to attach.
            env_vars: Environment variables.
            excluded_unhealthy: List of excluded unhealthy sandboxes.
            ttl_cleanup_applied: Whether TTL cleanup was applied before provisioning.
            stopped_sandbox_ids: List of sandbox IDs stopped during TTL cleanup.
            ttl_cleanup_reason: Reason for TTL cleanup.

        Returns:
            SandboxRoutingResult with provisioning outcome.
        """
        if stopped_sandbox_ids is None:
            stopped_sandbox_ids = []

        pack_source_path: Optional[str] = None
        pack_digest: Optional[str] = None

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
                    ttl_cleanup_applied=ttl_cleanup_applied,
                    stopped_sandbox_ids=stopped_sandbox_ids,
                    ttl_cleanup_reason=ttl_cleanup_reason,
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
                    ttl_cleanup_applied=ttl_cleanup_applied,
                    stopped_sandbox_ids=stopped_sandbox_ids,
                    ttl_cleanup_reason=ttl_cleanup_reason,
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
                    ttl_cleanup_applied=ttl_cleanup_applied,
                    stopped_sandbox_ids=stopped_sandbox_ids,
                    ttl_cleanup_reason=ttl_cleanup_reason,
                )

            # Validation: pack must be valid (not pending, invalid, or stale)
            # validation_status is stored as string in SQLite
            if pack.validation_status != AgentPackValidationStatus.VALID:
                return SandboxRoutingResult(
                    success=False,
                    result=RoutingResult.PROVISION_FAILED,
                    sandbox=None,
                    provider_info=None,
                    message=f"Agent pack {agent_pack_id} is not valid (status: {pack.validation_status})",
                    excluded_unhealthy=excluded_unhealthy,
                    ttl_cleanup_applied=ttl_cleanup_applied,
                    stopped_sandbox_ids=stopped_sandbox_ids,
                    ttl_cleanup_reason=ttl_cleanup_reason,
                )

            pack_source_path = pack.source_path
            pack_digest = pack.source_digest

        # Generate runtime bridge config for Picoclaw gateway
        runtime_bridge_config = self._generate_runtime_bridge_config(
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            env_vars=env_vars or {},
        )

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

            # Provision via provider with pack source path and runtime config
            config = SandboxConfig(
                workspace_id=workspace_id,
                idle_ttl_seconds=self._idle_ttl_seconds,
                env_vars=env_vars or {},
                pack_source_path=pack_source_path,
                pack_digest=pack_digest,
                runtime_bridge_config=runtime_bridge_config,
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
                ttl_cleanup_applied=ttl_cleanup_applied,
                stopped_sandbox_ids=stopped_sandbox_ids,
                ttl_cleanup_reason=ttl_cleanup_reason,
            )

        except Exception as e:
            return SandboxRoutingResult(
                success=False,
                result=RoutingResult.PROVISION_FAILED,
                sandbox=None,
                provider_info=None,
                message=f"Failed to provision sandbox: {str(e)}",
                excluded_unhealthy=excluded_unhealthy,
                ttl_cleanup_applied=ttl_cleanup_applied,
                stopped_sandbox_ids=stopped_sandbox_ids,
                ttl_cleanup_reason=ttl_cleanup_reason,
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

    def _generate_runtime_bridge_config(
        self,
        workspace_id: UUID,
        agent_pack_id: Optional[UUID],
        env_vars: Dict[str, str],
    ) -> Dict[str, Any]:
        """Generate runtime bridge configuration for Picoclaw gateway.

        This creates the per-sandbox configuration needed for the Picoclaw
        runtime to operate in bridge mode with isolated credentials.

        Args:
            workspace_id: Workspace UUID for scoping.
            agent_pack_id: Optional agent pack ID for workspace mapping.
            env_vars: Existing environment variables to include in config.

        Returns:
            Runtime bridge configuration dict for provider use.
        """
        import secrets

        # Generate unique bridge auth token for this sandbox
        bridge_auth_token = secrets.token_urlsafe(32)

        # Build the runtime config that providers will use to generate config.json
        config = {
            "workspace_id": str(workspace_id),
            "agent_pack_id": str(agent_pack_id) if agent_pack_id else None,
            "bridge": {
                "enabled": True,
                "auth_token": bridge_auth_token,
                # Gateway port - standard Picoclaw gateway port
                "gateway_port": 18790,
            },
            # Environment variables to inject (for sensitive credentials)
            # Note: Sensitive values should come from env vars, not be embedded
            "env_vars": env_vars,
            # Channel configuration - bridge-only, public channels disabled
            "channels": {
                "bridge": {"enabled": True},
                "telegram": {"enabled": False},
                "discord": {"enabled": False},
                "slack": {"enabled": False},
                "line": {"enabled": False},
                "wecom": {"enabled": False},
                "feishu": {"enabled": False},
                "dingtalk": {"enabled": False},
                "qq": {"enabled": False},
                "onebot": {"enabled": False},
                "whatsapp": {"enabled": False},
                "maixcam": {"enabled": False},
            },
            # Gateway configuration
            "gateway": {
                "host": "0.0.0.0",
                "port": 18790,
            },
        }

        return config
