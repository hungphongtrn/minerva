"""Local Docker Compose sandbox provider implementation.

This provider manages sandbox instances using local Docker Compose.
It's designed for local development and testing scenarios.
"""

import asyncio
import hashlib
import json
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


class LocalComposeSandboxProvider(SandboxProvider):
    """Sandbox provider using local Docker Compose.

    This provider simulates sandbox lifecycle for local development.
    In production implementations, this would manage actual Docker containers
    via Docker SDK or subprocess calls to docker-compose.

    For Phase 2, this provides the semantic contract implementation
    with in-memory state tracking for testing parity verification.
    """

    PROFILE = "local_compose"

    def __init__(self, compose_file_path: Optional[str] = None):
        """Initialize the local compose provider.

        Args:
            compose_file_path: Path to docker-compose.yml (optional)
        """
        self._compose_file_path = compose_file_path or "docker-compose.yml"
        self._sandboxes: Dict[str, Dict[str, Any]] = {}
        """In-memory sandbox registry for testing/development.
        
        Structure: {provider_ref: sandbox_data}
        sandbox_data contains:
        - workspace_id: UUID
        - state: SandboxState
        - health: SandboxHealth
        - created_at: datetime
        - last_activity_at: datetime
        - config: SandboxConfig
        """

    @property
    def profile(self) -> str:
        """Return the profile key for this provider."""
        return self.PROFILE

    def _generate_ref(self, workspace_id: UUID) -> str:
        """Generate a deterministic provider reference for a workspace."""
        # Create a short hash from workspace_id for readable refs
        hash_input = f"local-{workspace_id}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
        return f"local-sandbox-{short_hash}"

    def _to_info(self, ref: str, data: Dict[str, Any]) -> SandboxInfo:
        """Convert internal data to SandboxInfo DTO."""
        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=ref,
                profile=self.PROFILE,
                metadata={
                    "compose_file": self._compose_file_path,
                    "local_only": True,
                },
            ),
            state=data["state"],
            health=data["health"],
            workspace_id=data.get("workspace_id"),
            last_activity_at=data.get("last_activity_at"),
            created_at=data.get("created_at"),
            error_message=data.get("error_message"),
            provider_state=data.get("provider_state", "local_simulated"),
        )

    async def get_active_sandbox(
        self,
        workspace_id: UUID,
    ) -> Optional[SandboxInfo]:
        """Get active sandbox for workspace.

        Returns the sandbox if it exists and is not in terminal STOPPED state.
        """
        ref = self._generate_ref(workspace_id)

        if ref not in self._sandboxes:
            return None

        data = self._sandboxes[ref]

        # Return None if sandbox is stopped (terminal state)
        if data["state"] == SandboxState.STOPPED:
            return None

        return self._to_info(ref, data)

    async def provision_sandbox(
        self,
        config: SandboxConfig,
    ) -> SandboxInfo:
        """Create and start a new local sandbox.

        Simulates the provisioning lifecycle:
        1. Start in HYDRATING state
        2. Transition to READY after simulated startup
        3. Mark as HEALTHY
        """
        ref = self._generate_ref(config.workspace_id)

        # Check if sandbox already exists and is active
        if ref in self._sandboxes:
            existing = self._sandboxes[ref]
            if existing["state"] != SandboxState.STOPPED:
                raise SandboxProvisionError(
                    f"Sandbox already exists for workspace {config.workspace_id}",
                    provider_ref=ref,
                    workspace_id=config.workspace_id,
                )

        now = datetime.now(timezone.utc)

        # Start in HYDRATING state
        self._sandboxes[ref] = {
            "workspace_id": config.workspace_id,
            "state": SandboxState.HYDRATING,
            "health": SandboxHealth.UNKNOWN,
            "created_at": now,
            "last_activity_at": now,
            "config": config,
            "provider_state": "creating",
        }

        # Simulate async provisioning delay
        await asyncio.sleep(0.01)

        # Transition to READY
        self._sandboxes[ref]["state"] = SandboxState.READY
        self._sandboxes[ref]["health"] = SandboxHealth.HEALTHY
        self._sandboxes[ref]["provider_state"] = "running"

        return self._to_info(ref, self._sandboxes[ref])

    async def get_health(self, ref: SandboxRef) -> SandboxInfo:
        """Check current health and state.

        Performs a fresh health check simulation.
        Fail-closed: returns UNHEALTHY if sandbox unknown.
        """
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Sandbox {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]

        # Simulate health check
        # In real implementation, this would check container health
        if data["state"] == SandboxState.READY:
            # Default to healthy for ready sandboxes
            data["health"] = SandboxHealth.HEALTHY
        elif data["state"] == SandboxState.UNHEALTHY:
            data["health"] = SandboxHealth.UNHEALTHY

        return self._to_info(ref.provider_ref, data)

    async def stop_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        """Stop and terminate a sandbox.

        Idempotent: safe to call multiple times.
        """
        if ref.provider_ref not in self._sandboxes:
            # Idempotent: already gone, return stopped state
            return SandboxInfo(
                ref=SandboxRef(
                    provider_ref=ref.provider_ref,
                    profile=self.PROFILE,
                ),
                state=SandboxState.STOPPED,
                health=SandboxHealth.UNKNOWN,
                error_message="Sandbox not found (already stopped)",
            )

        data = self._sandboxes[ref.provider_ref]

        # Transition through STOPPING if not already stopped
        if data["state"] != SandboxState.STOPPED:
            data["state"] = SandboxState.STOPPING
            data["provider_state"] = "stopping"

            # Simulate stop delay
            await asyncio.sleep(0.01)

            data["state"] = SandboxState.STOPPED
            data["health"] = SandboxHealth.UNKNOWN
            data["provider_state"] = "stopped"

        return self._to_info(ref.provider_ref, data)

    async def attach_workspace(
        self,
        ref: SandboxRef,
        workspace_id: UUID,
    ) -> SandboxInfo:
        """Attach a workspace to a sandbox.

        For local compose, this validates the workspace matches
        the sandbox's original workspace.
        """
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Sandbox {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]

        # Verify workspace match
        existing_workspace = data.get("workspace_id")
        if existing_workspace and existing_workspace != workspace_id:
            raise SandboxConfigurationError(
                f"Sandbox {ref.provider_ref} already attached to workspace {existing_workspace}",
                provider_ref=ref.provider_ref,
                workspace_id=workspace_id,
            )

        data["workspace_id"] = workspace_id

        return self._to_info(ref.provider_ref, data)

    async def update_activity(self, ref: SandboxRef) -> SandboxInfo:
        """Update last activity timestamp."""
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Sandbox {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]
        data["last_activity_at"] = datetime.now(timezone.utc)

        return self._to_info(ref.provider_ref, data)

    # Additional methods for testing parity

    async def mark_unhealthy(self, ref: SandboxRef, reason: str = "") -> SandboxInfo:
        """Mark a sandbox as unhealthy (for testing)."""
        if ref.provider_ref not in self._sandboxes:
            raise SandboxNotFoundError(
                f"Sandbox {ref.provider_ref} not found",
                provider_ref=ref.provider_ref,
            )

        data = self._sandboxes[ref.provider_ref]
        data["state"] = SandboxState.UNHEALTHY
        data["health"] = SandboxHealth.UNHEALTHY
        data["error_message"] = reason or "Health check failed"
        data["provider_state"] = "unhealthy"

        return self._to_info(ref.provider_ref, data)
