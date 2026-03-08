"""Sandbox orchestrator service for health-aware routing and lifecycle management.

Provides service-level orchestration for sandbox selection, provisioning,
and idle TTL enforcement with health-aware routing decisions.

Key design: Single-attempt provisioning. No nested retry loops.
The orchestrator either finds an existing healthy sandbox or provisions
exactly one new sandbox. Failures fail fast without retry amplification.
"""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.db.models import (
    AgentPackValidationStatus,
    SandboxHealthStatus,
    SandboxHydrationStatus,
    SandboxInstance,
    SandboxProfile,
    SandboxState,
)
from src.db.repositories.agent_pack_repository import AgentPackRepository
from src.db.repositories.sandbox_instance_repository import SandboxInstanceRepository
from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxProvider,
    SandboxProviderError,
    SandboxRef,
)
from src.infrastructure.sandbox.providers.base import (
    SandboxHealth as ProviderSandboxHealth,
)
from src.infrastructure.sandbox.providers.factory import get_provider


class RoutingResult(Enum):
    """Result codes for sandbox routing operations."""

    ROUTED_EXISTING = auto()
    PROVISIONED_NEW = auto()
    HYDRATED_EXISTING = auto()
    UNHEALTHY_EXCLUDED = auto()
    NO_HEALTHY_CANDIDATES = auto()
    PROVISION_FAILED = auto()
    IDENTITY_CHECK_FAILED = auto()
    GATEWAY_RESOLUTION_FAILED = auto()


@dataclass
class SandboxRoutingResult:
    """Result of a sandbox routing attempt."""

    success: bool
    result: RoutingResult
    sandbox: SandboxInstance | None
    provider_info: SandboxInfo | None
    message: str
    excluded_unhealthy: list[SandboxInstance]
    ttl_cleanup_applied: bool = False
    stopped_sandbox_ids: list[str] | None = None
    ttl_cleanup_reason: str | None = None
    remediation: str | None = None
    reprovision_attempts: int = 0
    reprovision_exhausted: bool = False
    gateway_url: str | None = None

    def __post_init__(self):
        if self.stopped_sandbox_ids is None:
            self.stopped_sandbox_ids = []


@dataclass
class StopEligibilityResult:
    """Result of stop eligibility check."""

    eligible: bool
    reason: str
    idle_seconds: int | None
    ttl_seconds: int


@dataclass
class LayeredReadinessResult:
    """Result of layered readiness check for a sandbox."""

    is_request_ready: bool
    needs_hydration: bool
    failure_reason: str | None
    provider_info: SandboxInfo | None
    identity_ready: bool
    health_ready: bool


class SandboxOrchestratorService:
    """Service for sandbox lifecycle orchestration and routing.

    Core invariant: 1 user → 1 sandbox. No retry amplification.

    Flow:
    1. Stop idle sandboxes that exceeded TTL
    2. Find existing healthy sandbox → route to it
    3. No healthy sandbox → provision exactly one new sandbox
    4. If provisioning fails, fail fast (no retry loop)
    """

    DEFAULT_IDLE_TTL_SECONDS = 3600
    MIN_IDLE_TTL_SECONDS = 60
    MAX_IDLE_TTL_SECONDS = 86400

    EXISTING_SANDBOX_WAIT_SECONDS = 30
    EXISTING_SANDBOX_POLL_SECONDS = 0.25

    HYDRATION_TIMEOUT_SECONDS = 300

    def __init__(
        self,
        session: Session,
        provider: SandboxProvider | None = None,
        idle_ttl_seconds: int | None = None,
    ):
        self._session = session
        self._repository = SandboxInstanceRepository(session)
        self._provider = provider or get_provider()
        self._idle_ttl_seconds = self._validate_ttl(idle_ttl_seconds or self._get_configured_ttl())

    # ── Public API ───────────────────────────────────────────────

    async def resolve_sandbox(
        self,
        workspace_id: UUID,
        profile: SandboxProfile | None = None,
        agent_pack_id: UUID | None = None,
        env_vars: dict[str, str] | None = None,
        external_user_id: str | None = None,
    ) -> SandboxRoutingResult:
        """Resolve a sandbox for workspace execution.

        Single-attempt provisioning. No nested retries.
        """
        excluded_unhealthy: list[SandboxInstance] = []
        ttl_cleanup_applied = False
        stopped_sandbox_ids: list[str] = []
        ttl_cleanup_reason: str | None = None
        effective_profile = (
            profile
            or getattr(self._provider, "profile", None)
            or settings.SANDBOX_PROFILE
            or SandboxProfile.LOCAL_COMPOSE
        )

        try:
            # Step 1: Stop idle sandboxes
            stopped_idle = await self._stop_idle_sandboxes(workspace_id)
            if stopped_idle:
                ttl_cleanup_applied = True
                stopped_sandbox_ids = [str(s.id) for s in stopped_idle]
                ttl_cleanup_reason = (
                    f"Stopped {len(stopped_idle)} idle sandbox(s) "
                    f"exceeding TTL ({self._idle_ttl_seconds}s)"
                )

            # Step 2: Find active healthy sandbox
            active_sandboxes = self._repository.list_active_healthy_by_workspace(
                workspace_id=workspace_id,
                profile=effective_profile,
                external_user_id=external_user_id,
            )

            for sandbox in active_sandboxes:
                readiness = await self._check_readiness(sandbox)

                if readiness.is_request_ready:
                    self._repository.update_activity(sandbox.id)
                    if readiness.needs_hydration:
                        self._trigger_hydration(sandbox)
                    return self._ok(
                        RoutingResult.ROUTED_EXISTING,
                        sandbox,
                        readiness.provider_info,
                        f"Routed to request-ready sandbox {sandbox.id}",
                        excluded_unhealthy,
                        ttl_cleanup_applied,
                        stopped_sandbox_ids,
                        ttl_cleanup_reason,
                        gateway_url=sandbox.gateway_url,
                    )
                else:
                    self._mark_unhealthy(sandbox, readiness.failure_reason)
                    excluded_unhealthy.append(sandbox)

            # Step 3: No ready sandbox — provision one (single attempt)
            return await self._provision_sandbox(
                workspace_id=workspace_id,
                profile=effective_profile,
                agent_pack_id=agent_pack_id,
                env_vars=env_vars,
                external_user_id=external_user_id,
                excluded_unhealthy=excluded_unhealthy,
                ttl_cleanup_applied=ttl_cleanup_applied,
                stopped_sandbox_ids=stopped_sandbox_ids,
                ttl_cleanup_reason=ttl_cleanup_reason,
            )

        except Exception as e:
            return self._fail(
                RoutingResult.NO_HEALTHY_CANDIDATES,
                f"Sandbox resolution failed: {e}",
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
                remediation="Check provider health and retry",
            )

    def check_stop_eligibility(self, sandbox: SandboxInstance) -> StopEligibilityResult:
        """Check if a sandbox is eligible for idle stop."""
        if sandbox.state != SandboxState.ACTIVE:
            return StopEligibilityResult(
                eligible=False,
                reason=f"Sandbox is not active (state: {sandbox.state})",
                idle_seconds=None,
                ttl_seconds=self._idle_ttl_seconds,
            )

        last_activity = sandbox.last_activity_at or sandbox.created_at
        now = datetime.utcnow()
        idle_duration = (now - last_activity).total_seconds()
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
            reason=f"Sandbox active within TTL ({int(idle_duration)}s < {ttl}s)",
            idle_seconds=int(idle_duration),
            ttl_seconds=ttl,
        )

    async def stop_idle_sandboxes(self, workspace_id: UUID | None = None) -> list[SandboxInstance]:
        """Stop sandboxes that have exceeded idle TTL."""
        if not workspace_id:
            return []
        return await self._stop_idle_sandboxes(workspace_id)

    async def get_sandbox_health(self, sandbox_id: UUID) -> SandboxInfo | None:
        """Get current health for a sandbox."""
        sandbox = self._repository.get_by_id(sandbox_id)
        if not sandbox:
            return None
        return await self._check_provider_health(sandbox)

    def update_sandbox_activity(self, sandbox_id: UUID) -> SandboxInstance | None:
        """Update last activity timestamp for a sandbox."""
        return self._repository.update_activity(sandbox_id)

    def list_idle_sandboxes(self, workspace_id: UUID | None = None) -> list[SandboxInstance]:
        """List sandboxes eligible for idle stop."""
        if not workspace_id:
            return []
        candidates = self._repository.list_by_workspace(
            workspace_id=workspace_id, include_inactive=False
        )
        return [s for s in candidates if self.check_stop_eligibility(s).eligible]

    # ── Provisioning (single attempt) ────────────────────────────

    async def _provision_sandbox(
        self,
        workspace_id: UUID,
        profile: SandboxProfile,
        agent_pack_id: UUID | None,
        env_vars: dict[str, str] | None,
        external_user_id: str | None,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool = False,
        stopped_sandbox_ids: list[str] | None = None,
        ttl_cleanup_reason: str | None = None,
    ) -> SandboxRoutingResult:
        """Provision a new sandbox — single attempt, no retry loop.

        Deduplication is handled by _find_in_progress_sandbox + DB unique constraint.
        """
        if stopped_sandbox_ids is None:
            stopped_sandbox_ids = []

        # Validate agent pack if provided
        pack_source_path, pack_digest = None, None
        if agent_pack_id:
            pack_result = self._validate_agent_pack(
                agent_pack_id,
                workspace_id,
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
            )
            if isinstance(pack_result, SandboxRoutingResult):
                return pack_result  # Validation failed
            pack_source_path, pack_digest = pack_result

        # Generate bridge auth token
        bridge_auth_token = secrets.token_urlsafe(32)

        # Generate runtime config
        runtime_bridge_config = self._generate_runtime_bridge_config(
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            env_vars=env_vars or {},
            bridge_auth_token=bridge_auth_token,
        )

        sandbox: SandboxInstance | None = None
        gateway_url: str | None = None

        try:
            # Check for existing in-progress sandbox (dedup)
            existing = self._find_in_progress_sandbox(
                workspace_id, profile, agent_pack_id, external_user_id
            )

            if existing:
                result = await self._handle_existing_sandbox(
                    existing,
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                )
                if result:
                    return result
                sandbox = existing
            else:
                sandbox = self._create_sandbox_record(
                    workspace_id,
                    profile,
                    agent_pack_id,
                    external_user_id,
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                )
                if isinstance(sandbox, SandboxRoutingResult):
                    return sandbox  # Creation failed (race condition)

            # Provision via provider
            config = SandboxConfig(
                workspace_id=workspace_id,
                external_user_id=external_user_id,
                idle_ttl_seconds=self._idle_ttl_seconds,
                env_vars=env_vars or {},
                pack_source_path=pack_source_path,
                pack_digest=pack_digest,
                runtime_bridge_config=runtime_bridge_config,
                agent_pack_id=agent_pack_id,
            )

            provider_info = await self._provider.provision_sandbox(config)

            # Update sandbox with provider info
            if provider_info and provider_info.ref:
                gateway_url = self._finalize_provisioning(
                    sandbox, provider_info, profile, bridge_auth_token
                )

            return self._ok(
                RoutingResult.PROVISIONED_NEW,
                sandbox,
                provider_info,
                f"Provisioned new sandbox {sandbox.id}",
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
                gateway_url=gateway_url,
            )

        except Exception as e:
            if sandbox is not None:
                self._mark_sandbox_failed(sandbox, e)
            return self._fail(
                RoutingResult.PROVISION_FAILED,
                f"Failed to provision sandbox: {e}",
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
            )

    # ── Deduplication ────────────────────────────────────────────

    def _find_in_progress_sandbox(
        self,
        workspace_id: UUID,
        profile: SandboxProfile,
        agent_pack_id: UUID | None,
        external_user_id: str | None,
    ) -> SandboxInstance | None:
        """Find an existing PENDING/CREATING sandbox to avoid duplicates."""
        conditions = [
            SandboxInstance.workspace_id == workspace_id,
            SandboxInstance.profile == profile,
            SandboxInstance.state.in_([SandboxState.PENDING, SandboxState.CREATING]),
        ]
        if agent_pack_id is not None:
            conditions.append(SandboxInstance.agent_pack_id == agent_pack_id)
        if external_user_id is not None:
            conditions.append(SandboxInstance.external_user_id == external_user_id)

        stmt = (
            select(SandboxInstance)
            .where(and_(*conditions))
            .order_by(SandboxInstance.created_at.desc())
        )
        return self._session.execute(stmt).scalars().first()

    async def _wait_for_existing_sandbox_activation(
        self, sandbox_id: UUID
    ) -> SandboxInstance | None:
        """Wait for an in-progress sandbox to become active."""
        deadline = asyncio.get_event_loop().time() + self.EXISTING_SANDBOX_WAIT_SECONDS

        while asyncio.get_event_loop().time() < deadline:
            sandbox = self._repository.get_by_id(sandbox_id)
            if not sandbox:
                return None
            if sandbox.state == SandboxState.ACTIVE and sandbox.provider_ref:
                return sandbox
            if sandbox.state in (
                SandboxState.UNHEALTHY,
                SandboxState.STOPPING,
                SandboxState.STOPPED,
                SandboxState.FAILED,
            ):
                return None
            await asyncio.sleep(self.EXISTING_SANDBOX_POLL_SECONDS)

        return None

    async def _handle_existing_sandbox(
        self,
        existing: SandboxInstance,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool,
        stopped_sandbox_ids: list[str],
        ttl_cleanup_reason: str | None,
    ) -> SandboxRoutingResult | None:
        """Handle an existing in-progress or active sandbox. Returns result or None."""
        if existing.state in (SandboxState.PENDING, SandboxState.CREATING):
            activated = await self._wait_for_existing_sandbox_activation(existing.id)
            if activated:
                return self._ok(
                    RoutingResult.ROUTED_EXISTING,
                    activated,
                    None,
                    f"Reused concurrently provisioned sandbox {activated.id}",
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                    gateway_url=activated.gateway_url,
                )

        if existing.state == SandboxState.ACTIVE and existing.provider_ref:
            return self._ok(
                RoutingResult.ROUTED_EXISTING,
                existing,
                None,
                f"Reused active sandbox {existing.id}",
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
                gateway_url=existing.gateway_url,
            )

        return None  # Fall through to provisioning

    def _create_sandbox_record(
        self,
        workspace_id: UUID,
        profile: SandboxProfile,
        agent_pack_id: UUID | None,
        external_user_id: str | None,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool,
        stopped_sandbox_ids: list[str],
        ttl_cleanup_reason: str | None,
    ):
        """Create DB record for new sandbox. Returns SandboxInstance or SandboxRoutingResult on failure."""
        try:
            sandbox = self._repository.create(
                workspace_id=workspace_id,
                profile=profile,
                agent_pack_id=agent_pack_id,
                idle_ttl_seconds=self._idle_ttl_seconds,
                external_user_id=external_user_id,
            )
            self._repository.update_state(sandbox.id, SandboxState.CREATING)
            sandbox_id = sandbox.id
            self._session.commit()

            sandbox = self._repository.get_by_id(sandbox_id)
            if sandbox is None:
                return self._fail(
                    RoutingResult.PROVISION_FAILED,
                    "Sandbox DB row was not persisted",
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                )
            return sandbox

        except IntegrityError:
            self._session.rollback()
            raced = self._find_in_progress_sandbox(
                workspace_id, profile, agent_pack_id, external_user_id
            )
            if raced:
                # Another request won the race — try to wait for activation
                # We do NOT provision again (prevents multi-sandbox)
                return self._fail(
                    RoutingResult.PROVISION_FAILED,
                    f"Concurrent sandbox creation detected (raced sandbox {raced.id})",
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                )
            return self._fail(
                RoutingResult.PROVISION_FAILED,
                "Concurrent sandbox creation detected — activation did not complete",
                excluded_unhealthy,
                ttl_cleanup_applied,
                stopped_sandbox_ids,
                ttl_cleanup_reason,
            )

    # ── Readiness & Health ───────────────────────────────────────

    async def _check_readiness(self, sandbox: SandboxInstance) -> LayeredReadinessResult:
        """Check layered readiness: identity → health."""
        if not sandbox.identity_ready:
            return LayeredReadinessResult(
                is_request_ready=False,
                needs_hydration=False,
                failure_reason="Identity files not mounted",
                provider_info=None,
                identity_ready=False,
                health_ready=False,
            )

        provider_info = await self._check_provider_health(sandbox)
        if not provider_info:
            return LayeredReadinessResult(
                is_request_ready=False,
                needs_hydration=True,
                failure_reason="Health check failed",
                provider_info=None,
                identity_ready=True,
                health_ready=False,
            )
        if provider_info.health != ProviderSandboxHealth.HEALTHY:
            return LayeredReadinessResult(
                is_request_ready=False,
                needs_hydration=True,
                failure_reason=f"Sandbox unhealthy: {provider_info.health}",
                provider_info=provider_info,
                identity_ready=True,
                health_ready=False,
            )

        needs_hydration = sandbox.hydration_status in (
            SandboxHydrationStatus.PENDING,
            SandboxHydrationStatus.IN_PROGRESS,
        )
        return LayeredReadinessResult(
            is_request_ready=True,
            needs_hydration=needs_hydration,
            failure_reason=None,
            provider_info=provider_info,
            identity_ready=True,
            health_ready=True,
        )

    async def _check_provider_health(self, sandbox: SandboxInstance) -> SandboxInfo | None:
        """Check health via provider."""
        if not sandbox.provider_ref:
            return None
        try:
            ref = SandboxRef(
                provider_ref=sandbox.provider_ref,
                profile=sandbox.profile,
            )
            return await self._provider.get_health(ref)
        except (SandboxNotFoundError, SandboxProviderError):
            return None

    def _mark_unhealthy(self, sandbox: SandboxInstance, reason: str | None = None) -> None:
        """Mark sandbox as unhealthy in the database."""
        self._repository.update_health(sandbox.id, SandboxHealthStatus.UNHEALTHY)
        self._repository.update_state(sandbox.id, SandboxState.UNHEALTHY)

    def _trigger_hydration(self, sandbox: SandboxInstance) -> None:
        """Trigger async checkpoint hydration (non-blocking)."""
        self._repository.set_hydration_status(sandbox.id, SandboxHydrationStatus.IN_PROGRESS)
        # Production: use a task queue. For now, mark completed.
        self._repository.set_hydration_status(sandbox.id, SandboxHydrationStatus.COMPLETED)

    # ── Idle TTL Enforcement ─────────────────────────────────────

    async def _stop_idle_sandboxes(self, workspace_id: UUID) -> list[SandboxInstance]:
        """Stop sandboxes that exceeded TTL."""
        candidates = self._repository.list_by_workspace(
            workspace_id=workspace_id, include_inactive=False
        )
        stopped = []
        for sandbox in candidates:
            if self.check_stop_eligibility(sandbox).eligible:
                result = await self._stop_sandbox(sandbox)
                if result:
                    stopped.append(result)
        return stopped

    async def _stop_sandbox(self, sandbox: SandboxInstance) -> SandboxInstance | None:
        """Stop a sandbox (idempotent)."""
        try:
            self._repository.update_state(sandbox.id, SandboxState.STOPPING)
            if sandbox.provider_ref:
                try:
                    ref = SandboxRef(
                        provider_ref=sandbox.provider_ref,
                        profile=sandbox.profile,
                    )
                    await self._provider.stop_sandbox(ref)
                except SandboxNotFoundError:
                    pass
            return self._repository.update_state(sandbox.id, SandboxState.STOPPED)
        except Exception:
            self._repository.update_state(sandbox.id, SandboxState.FAILED)
            return None

    # ── Pack Validation ──────────────────────────────────────────

    def _validate_agent_pack(
        self,
        agent_pack_id: UUID,
        workspace_id: UUID,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool,
        stopped_sandbox_ids: list[str],
        ttl_cleanup_reason: str | None,
    ):
        """Validate agent pack. Returns (source_path, digest) or SandboxRoutingResult on failure."""
        pack_repo = AgentPackRepository(self._session)
        pack = pack_repo.get_by_id(agent_pack_id)

        checks = [
            (not pack, f"Agent pack not found: {agent_pack_id}"),
            (
                pack and pack.workspace_id != workspace_id,
                f"Agent pack {agent_pack_id} does not belong to workspace {workspace_id}",
            ),
            (pack and not pack.is_active, f"Agent pack {agent_pack_id} is not active"),
            (
                pack and pack.validation_status != AgentPackValidationStatus.VALID,
                f"Agent pack {agent_pack_id} is not valid (status: {getattr(pack, 'validation_status', 'unknown')})",
            ),
        ]
        for condition, msg in checks:
            if condition:
                return self._fail(
                    RoutingResult.PROVISION_FAILED,
                    msg,
                    excluded_unhealthy,
                    ttl_cleanup_applied,
                    stopped_sandbox_ids,
                    ttl_cleanup_reason,
                )

        return (pack.source_path, pack.source_digest)

    # ── Finalization ─────────────────────────────────────────────

    def _finalize_provisioning(
        self,
        sandbox: SandboxInstance,
        provider_info: SandboxInfo,
        profile: SandboxProfile,
        bridge_auth_token: str,
    ) -> str | None:
        """Update sandbox record after successful provisioning."""
        self._repository.set_provider_ref(sandbox.id, provider_info.ref.provider_ref)

        gateway_url = provider_info.ref.metadata.get("gateway_url")
        if not gateway_url:
            gateway_url = self._generate_gateway_url(profile, provider_info.ref.provider_ref)
        if gateway_url:
            self._repository.set_gateway_url_authoritative(sandbox.id, gateway_url)

        self._repository.rotate_bridge_token(sandbox.id, bridge_auth_token, grace_seconds=30)
        self._repository.set_identity_ready(sandbox.id, ready=True)

        runtime_ready = bool(provider_info.ref.metadata.get("runtime_ready"))
        self._repository.set_hydration_status(
            sandbox.id,
            SandboxHydrationStatus.COMPLETED if runtime_ready else SandboxHydrationStatus.PENDING,
        )

        self._repository.update_state(sandbox.id, SandboxState.ACTIVE)
        self._repository.update_health(sandbox.id, SandboxHealthStatus.HEALTHY)
        self._repository.update_activity(sandbox.id)
        self._session.commit()

        return gateway_url

    def _mark_sandbox_failed(self, sandbox: SandboxInstance, error: Exception) -> None:
        """Mark sandbox as FAILED after provisioning error."""
        self._repository.increment_hydration_retry(sandbox.id, error=str(error))
        self._repository.set_hydration_status(
            sandbox.id,
            SandboxHydrationStatus.FAILED,
            last_error=str(error),
        )
        self._repository.update_health(sandbox.id, SandboxHealthStatus.UNHEALTHY)
        self._repository.update_state(sandbox.id, SandboxState.FAILED)
        self._session.commit()

    # ── Config Generation ────────────────────────────────────────

    def _generate_runtime_bridge_config(
        self,
        workspace_id: UUID,
        agent_pack_id: UUID | None,
        env_vars: dict[str, str],
        bridge_auth_token: str,
    ) -> dict[str, Any]:
        """Generate runtime bridge config for sandbox gateway."""
        from src.integrations.sandbox_runtime.spec import load_runtime_spec

        spec = load_runtime_spec()

        return {
            "workspace_id": str(workspace_id),
            "agent_pack_id": str(agent_pack_id) if agent_pack_id else None,
            "bridge": {
                "enabled": True,
                "auth_token": bridge_auth_token,
                "auth_mode": spec.auth.mode,
                "gateway_port": spec.gateway.port,
            },
            "env_vars": env_vars,
            "gateway": {
                "host": "0.0.0.0",
                "port": spec.gateway.port,
                "health_path": spec.gateway.health_path,
                "execute_path": spec.gateway.execute_path,
                "stream_mode": spec.gateway.stream_mode,
            },
            "runtime": {
                "config_path": spec.runtime.config_path,
                "start_command": spec.runtime.start_command,
            },
        }

    def _generate_gateway_url(self, profile: SandboxProfile, provider_ref: str) -> str | None:
        """Generate gateway URL for a sandbox."""
        if profile == SandboxProfile.LOCAL_COMPOSE:
            return f"http://{provider_ref}:18790"
        return None  # Daytona URLs come from provider

    # ── Helpers ──────────────────────────────────────────────────

    def _get_configured_ttl(self) -> int:
        ttl = getattr(settings, "SANDBOX_IDLE_TTL_SECONDS", None)
        return int(ttl) if ttl is not None else self.DEFAULT_IDLE_TTL_SECONDS

    @staticmethod
    def _validate_ttl(ttl_seconds: int) -> int:
        if ttl_seconds < SandboxOrchestratorService.MIN_IDLE_TTL_SECONDS:
            raise ValueError(
                f"Idle TTL must be >= {SandboxOrchestratorService.MIN_IDLE_TTL_SECONDS}s"
            )
        if ttl_seconds > SandboxOrchestratorService.MAX_IDLE_TTL_SECONDS:
            raise ValueError(
                f"Idle TTL must be <= {SandboxOrchestratorService.MAX_IDLE_TTL_SECONDS}s"
            )
        return ttl_seconds

    def _ok(
        self,
        result: RoutingResult,
        sandbox: SandboxInstance | None,
        provider_info: SandboxInfo | None,
        message: str,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool = False,
        stopped_sandbox_ids: list[str] | None = None,
        ttl_cleanup_reason: str | None = None,
        remediation: str | None = None,
        gateway_url: str | None = None,
    ) -> SandboxRoutingResult:
        """Build a success SandboxRoutingResult."""
        return SandboxRoutingResult(
            success=True,
            result=result,
            sandbox=sandbox,
            provider_info=provider_info,
            message=message,
            excluded_unhealthy=excluded_unhealthy,
            ttl_cleanup_applied=ttl_cleanup_applied,
            stopped_sandbox_ids=stopped_sandbox_ids or [],
            ttl_cleanup_reason=ttl_cleanup_reason,
            remediation=remediation,
            gateway_url=gateway_url,
        )

    def _fail(
        self,
        result: RoutingResult,
        message: str,
        excluded_unhealthy: list[SandboxInstance],
        ttl_cleanup_applied: bool = False,
        stopped_sandbox_ids: list[str] | None = None,
        ttl_cleanup_reason: str | None = None,
        remediation: str | None = None,
        sandbox: SandboxInstance | None = None,
    ) -> SandboxRoutingResult:
        """Build a failure SandboxRoutingResult."""
        return SandboxRoutingResult(
            success=False,
            result=result,
            sandbox=sandbox,
            provider_info=None,
            message=message,
            excluded_unhealthy=excluded_unhealthy,
            ttl_cleanup_applied=ttl_cleanup_applied,
            stopped_sandbox_ids=stopped_sandbox_ids or [],
            ttl_cleanup_reason=ttl_cleanup_reason,
            remediation=remediation,
        )
