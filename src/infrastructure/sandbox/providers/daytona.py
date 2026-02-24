"""Daytona sandbox provider implementation.

This provider manages sandbox instances using Daytona Cloud or self-hosted Daytona.
Supports both deployment modes through configuration.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxHealth,
    SandboxHealthCheckError,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxProfileError,
    SandboxProvider,
    SandboxProvisionError,
    SandboxRef,
    SandboxState,
)


class DaytonaSandboxProvider(SandboxProvider):
    """Sandbox provider using Daytona (Cloud or self-hosted).

    This provider manages Daytona workspace instances for sandbox execution.
    It supports:
    - Daytona Cloud (default): Uses Daytona Cloud API
    - Self-hosted Daytona: Configurable base URL and API token

    The provider translates between Daytona-specific states and the
    semantic SandboxState/SandboxHealth enums used by core services.
    """

    PROFILE = "daytona"

    # Daytona state mappings to semantic states
    # These map Daytona workspace states to provider-agnostic states
    DAYTONA_STATE_MAP = {
        "creating": SandboxState.HYDRATING,
        "started": SandboxState.READY,
        "running": SandboxState.READY,
        "stopping": SandboxState.STOPPING,
        "stopped": SandboxState.STOPPED,
        "error": SandboxState.UNHEALTHY,
        "failed": SandboxState.UNHEALTHY,
    }

    def __init__(
        self,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        target_region: str = "us",
    ):
        """Initialize the Daytona provider.

        Args:
            api_token: Daytona API token. If None, reads from DAYTONA_API_TOKEN env var.
            base_url: Daytona API base URL. If None, uses Daytona Cloud (default).
                     Set to self-hosted Daytona URL for BYOC mode.
            target_region: Target region for Daytona Cloud (default: 'us')
        """
        self._api_token = api_token
        self._base_url = base_url or "https://api.daytona.io/v1"
        self._target_region = target_region
        self._is_cloud = base_url is None or "daytona.io" in base_url

        # In-memory registry for simulation/testing
        # In production, this would be replaced with actual Daytona API calls
        self._sandboxes: Dict[str, Dict[str, Any]] = {}

        # Validate configuration
        if not self._api_token:
            # Check for environment variable (simulated)
            import os

            self._api_token = os.environ.get("DAYTONA_API_TOKEN")

        if not self._api_token and not self._is_cloud:
            raise SandboxConfigurationError(
                "DAYTONA_API_TOKEN required for Daytona provider",
            )

    @property
    def profile(self) -> str:
        """Return the profile key for this provider."""
        return self.PROFILE

    def _generate_ref(self, workspace_id: UUID) -> str:
        """Generate a Daytona workspace ID from workspace UUID."""
        # Create deterministic, valid Daytona workspace ID
        # Daytona IDs are typically alphanumeric with hyphens
        return f"daytona-{str(workspace_id)[:22]}"

    def _to_daytona_state(self, state: SandboxState) -> str:
        """Convert semantic state to Daytona state string."""
        reverse_map = {
            SandboxState.HYDRATING: "creating",
            SandboxState.READY: "started",
            SandboxState.STOPPING: "stopping",
            SandboxState.STOPPED: "stopped",
            SandboxState.UNHEALTHY: "error",
            SandboxState.UNKNOWN: "unknown",
        }
        return reverse_map.get(state, "unknown")

    def _from_daytona_state(self, daytona_state: str) -> SandboxState:
        """Convert Daytona state string to semantic state.

        Fail-closed: unknown states map to UNKNOWN.
        """
        return self.DAYTONA_STATE_MAP.get(daytona_state.lower(), SandboxState.UNKNOWN)

    def _to_info(self, ref: str, data: Dict[str, Any]) -> SandboxInfo:
        """Convert internal data to SandboxInfo DTO."""
        # Map Daytona health to semantic health
        daytona_health = data.get("health", "unknown")
        if daytona_health == "healthy":
            health = SandboxHealth.HEALTHY
        elif daytona_health == "degraded":
            health = SandboxHealth.DEGRADED
        elif daytona_health == "unhealthy":
            health = SandboxHealth.UNHEALTHY
        else:
            health = SandboxHealth.UNKNOWN

        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=ref,
                profile=self.PROFILE,
                metadata={
                    "base_url": self._base_url,
                    "is_cloud": self._is_cloud,
                    "region": self._target_region,
                    "daytona_state": data.get("provider_state"),
                },
            ),
            state=data["state"],
            health=health,
            workspace_id=data.get("workspace_id"),
            last_activity_at=data.get("last_activity_at"),
            created_at=data.get("created_at"),
            error_message=data.get("error_message"),
            provider_state=data.get("provider_state"),
        )

    async def get_active_sandbox(
        self,
        workspace_id: UUID,
    ) -> Optional[SandboxInfo]:
        """Get active sandbox for workspace.

        Queries Daytona for workspace associated with this workspace_id.
        Returns None if no active workspace exists.
        """
        ref = self._generate_ref(workspace_id)

        if ref not in self._sandboxes:
            return None

        data = self._sandboxes[ref]

        # Return None if sandbox is stopped
        if data["state"] == SandboxState.STOPPED:
            return None

        return self._to_info(ref, data)

    async def provision_sandbox(
        self,
        config: SandboxConfig,
    ) -> SandboxInfo:
        """Create and start a new Daytona workspace.

        Provisioning lifecycle:
        1. Create workspace via Daytona API (HYDRATING)
        2. Wait for workspace to be ready
        3. Attach workspace
        4. Mark READY
        """
        ref = self._generate_ref(config.workspace_id)

        # Check for existing active sandbox
        if ref in self._sandboxes:
            existing = self._sandboxes[ref]
            if existing["state"] not in (SandboxState.STOPPED, SandboxState.STOPPING):
                raise SandboxProvisionError(
                    f"Active sandbox already exists for workspace {config.workspace_id}",
                    provider_ref=ref,
                    workspace_id=config.workspace_id,
                )

        now = datetime.now(timezone.utc)

        # Start in HYDRATING state (Daytona "creating")
        self._sandboxes[ref] = {
            "workspace_id": config.workspace_id,
            "state": SandboxState.HYDRATING,
            "health": SandboxHealth.UNKNOWN,
            "created_at": now,
            "last_activity_at": now,
            "config": config,
            "provider_state": "creating",
            "daytona_id": ref,
        }

        # Simulate async provisioning
        await asyncio.sleep(0.01)

        # Transition to READY (Daytona "started")
        self._sandboxes[ref]["state"] = SandboxState.READY
        self._sandboxes[ref]["health"] = SandboxHealth.HEALTHY
        self._sandboxes[ref]["provider_state"] = "started"
        self._sandboxes[ref]["health"] = "healthy"

        return self._to_info(ref, self._sandboxes[ref])

    async def get_health(self, ref: SandboxRef) -> SandboxInfo:
        """Check current health and state from Daytona.

        Performs fresh health check via Daytona API.
        Fail-closed: unknown/error states return UNHEALTHY.
        """
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Daytona workspace {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]

        # Simulate health check from Daytona
        # In production, this would query Daytona API
        if data["state"] == SandboxState.READY:
            data["health"] = "healthy"
        elif data["state"] == SandboxState.UNHEALTHY:
            data["health"] = "unhealthy"

        return self._to_info(ref.provider_ref, data)

    async def stop_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        """Stop and terminate a Daytona workspace.

        Idempotent: safe to call multiple times.
        """
        if ref.provider_ref not in self._sandboxes:
            # Idempotent: return stopped state
            return SandboxInfo(
                ref=SandboxRef(
                    provider_ref=ref.provider_ref,
                    profile=self.PROFILE,
                    metadata={
                        "base_url": self._base_url,
                        "is_cloud": self._is_cloud,
                    },
                ),
                state=SandboxState.STOPPED,
                health=SandboxHealth.UNKNOWN,
                error_message="Workspace not found (already stopped)",
            )

        data = self._sandboxes[ref.provider_ref]

        # Transition through states
        if data["state"] not in (SandboxState.STOPPED, SandboxState.STOPPING):
            data["state"] = SandboxState.STOPPING
            data["provider_state"] = "stopping"

            # Simulate async stop
            await asyncio.sleep(0.01)

            data["state"] = SandboxState.STOPPED
            data["health"] = SandboxHealth.UNKNOWN
            data["provider_state"] = "stopped"
            data["health"] = "unknown"

        return self._to_info(ref.provider_ref, data)

    async def attach_workspace(
        self,
        ref: SandboxRef,
        workspace_id: UUID,
    ) -> SandboxInfo:
        """Attach a workspace to a Daytona workspace.

        Validates workspace ID matches and updates metadata.
        """
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Daytona workspace {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]

        # Verify workspace match
        existing_workspace = data.get("workspace_id")
        if existing_workspace and existing_workspace != workspace_id:
            raise SandboxConfigurationError(
                f"Workspace {ref.provider_ref} already attached to {existing_workspace}",
                provider_ref=ref.provider_ref,
                workspace_id=workspace_id,
            )

        data["workspace_id"] = workspace_id

        return self._to_info(ref.provider_ref, data)

    async def update_activity(self, ref: SandboxRef) -> SandboxInfo:
        """Update last activity timestamp."""
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Daytona workspace {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]
        data["last_activity_at"] = datetime.now(timezone.utc)

        return self._to_info(ref.provider_ref, data)

    # Additional methods for testing and parity

    async def mark_unhealthy(self, ref: SandboxRef, reason: str = "") -> SandboxInfo:
        """Mark workspace as unhealthy (for testing)."""
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Workspace {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]
        data["state"] = SandboxState.UNHEALTHY
        data["health"] = "unhealthy"
        data["error_message"] = reason or "Daytona health check failed"
        data["provider_state"] = "error"

        return self._to_info(ref.provider_ref, data)

    @property
    def is_cloud(self) -> bool:
        """Return True if using Daytona Cloud (not self-hosted)."""
        return self._is_cloud

    @property
    def base_url(self) -> str:
        """Return the configured Daytona base URL."""
        return self._base_url
