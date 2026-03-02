"""Local Docker Compose sandbox provider implementation.

This provider manages sandbox instances using local Docker Compose.
It's designed for local development and testing scenarios.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxHealth,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxProvider,
    SandboxProvisionError,
    SandboxRef,
    SandboxState,
    WORKSPACE_PATH,
    PACK_MOUNT_PATH,
    CONFIG_PATH,
    IDENTITY_FILES,
    IDENTITY_DIRS,
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
        # Pack binding metadata for observability and parity assertions
        pack_bound = data.get("pack_bound", False)
        pack_source_path = data.get("pack_source_path")
        pack_digest = data.get("pack_digest")
        materialized_config_path = data.get("materialized_config_path")

        metadata = {
            "compose_file": self._compose_file_path,
            "local_only": True,
            "pack_bound": pack_bound,
            "workspace_path": data.get("workspace_path", WORKSPACE_PATH),
            "pack_mount_path": data.get("pack_mount_path", PACK_MOUNT_PATH),
            "workspace_symlinks_created": data.get("workspace_symlinks_created", False),
        }

        if pack_bound and pack_source_path:
            metadata["pack_source_path"] = pack_source_path
            # Pack mount isolation contract: always expose read-only status
            metadata["pack_mount_read_only"] = True
        if pack_digest:
            metadata["pack_digest"] = pack_digest
        if materialized_config_path:
            metadata["materialized_config_path"] = materialized_config_path

        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=ref,
                profile=self.PROFILE,
                metadata=metadata,
            ),
            state=data["state"],
            health=data["health"],
            workspace_id=data.get("workspace_id"),
            last_activity_at=data.get("last_activity_at"),
            created_at=data.get("created_at"),
            error_message=data.get("error_message"),
            provider_state=data.get("provider_state", "local_simulated"),
        )

    def _generate_user_ref(self, workspace_id: UUID, external_user_id: str) -> str:
        """Generate a deterministic provider reference for per-user sandbox isolation.

        Each (workspace_id, external_user_id) pair gets its own sandbox,
        enabling multi-user isolation within the same workspace context.

        Args:
            workspace_id: The workspace UUID
            external_user_id: The external end-user identifier

        Returns:
            Deterministic provider reference string
        """
        hash_input = f"local-{workspace_id}-{external_user_id}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
        return f"local-sandbox-{short_hash}"

    async def _create_workspace_symlinks(self, ref: str) -> None:
        """Create workspace directory and symlink identity files (simulation).

        In production Docker implementation, this would:
        1. docker exec to create /home/daytona/workspace
        2. docker exec to create symlinks from /workspace/pack/{file} to /home/daytona/workspace/{file}

        For simulation, records that symlinks were configured in sandbox metadata.
        """
        if ref in self._sandboxes:
            self._sandboxes[ref]["workspace_symlinks_created"] = True
            self._sandboxes[ref]["workspace_path"] = WORKSPACE_PATH
            self._sandboxes[ref]["pack_mount_path"] = PACK_MOUNT_PATH

    def _generate_picoclaw_config(
        self,
        config: SandboxConfig,
    ) -> Dict[str, Any]:
        """Generate Picoclaw config.json for sandbox.

        Creates a deterministic, sandbox-scoped config with:
        - Bridge-only channels (public channels disabled)
        - Credentials from environment variables
        - Pack workspace mapping

        Args:
            config: Sandbox configuration with runtime_bridge_config.

        Returns:
            Complete Picoclaw config dict.
        """
        # Get runtime bridge config from orchestrator
        runtime_config = config.runtime_bridge_config or {}

        # Extract bridge settings
        bridge_config = runtime_config.get("bridge", {})
        bridge_auth_token = bridge_config.get("auth_token", "temp-token")
        gateway_port = bridge_config.get("gateway_port", 18790)

        # Build Picoclaw config.json structure
        picoclaw_config = {
            "agents": {
                "defaults": {
                    "workspace": WORKSPACE_PATH,
                    "restrict_to_workspace": True,
                    "model": "primary",
                    "max_tokens": 8192,
                    "temperature": 0.7,
                    "max_tool_iterations": 20,
                }
            },
            "model_list": [
                {
                    "model_name": "primary",
                    "model": "${LLM_MODEL:-openai/gpt-4}",
                    "api_key": "${LLM_API_KEY}",
                    "api_base": "${LLM_API_BASE}",
                }
            ],
            "channels": {
                "bridge": {
                    "enabled": True,
                    "auth_token": bridge_auth_token,
                },
                # All public channels disabled for security
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
            "gateway": {
                "host": "0.0.0.0",
                "port": gateway_port,
            },
            "heartbeat": {
                "enabled": False,
            },
        }

        return picoclaw_config

    async def _materialize_pack(
        self,
        config: SandboxConfig,
    ) -> Dict[str, Any]:
        """Materialize agent pack into sandbox workspace.

        Implements snapshot copy/sync semantics (not live bind).
        In production, this would copy pack files to a volume mount.

        Args:
            config: Sandbox configuration with pack_source_path.

        Returns:
            Materialization metadata with paths and digests.
        """
        if not config.pack_source_path:
            return {"materialized": False}

        # In production, this would:
        # 1. Copy pack_source_path contents to sandbox volume
        # 2. Compute digest of copied content
        # 3. Store config.json alongside pack

        # For local compose simulation:
        # - Track that materialization occurred
        # - Store the expected config path (outside pack volume for isolation)
        # - Store the pack digest for stale detection

        materialized_path = PACK_MOUNT_PATH
        config_path = CONFIG_PATH  # Outside pack volume for isolation parity

        return {
            "materialized": True,
            "source_path": config.pack_source_path,
            "materialized_path": materialized_path,
            "config_path": config_path,
            "pack_digest": config.pack_digest,
            "materialization_type": "snapshot_copy",
        }

    async def get_active_sandbox(
        self,
        workspace_id: UUID,
        external_user_id: Optional[str] = None,
    ) -> Optional[SandboxInfo]:
        """Get active sandbox for workspace.

        Returns the sandbox if it exists and is not in terminal STOPPED state.

        Args:
            workspace_id: The workspace to look up
            external_user_id: Optional external user ID for per-user sandbox isolation

        Returns:
            SandboxInfo if active sandbox exists, None otherwise
        """
        # Use per-user ref if external_user_id is provided
        if external_user_id:
            ref = self._generate_user_ref(workspace_id, external_user_id)
        else:
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
        2. Materialize pack (snapshot copy, not live bind)
        3. Generate Picoclaw config.json with bridge-only channels
        4. Transition to READY after simulated startup
        5. Mark as HEALTHY

        Pack binding:
        - If config.pack_source_path is provided, materializes pack into sandbox
        - Generates per-sandbox Picoclaw config.json with bridge-only channels
        - Pack digest stored in metadata for stale detection
        - Sensitive credentials remain env-var sourced
        """
        # Use per-user ref if external_user_id is set
        if config.external_user_id:
            ref = self._generate_user_ref(config.workspace_id, config.external_user_id)
        else:
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

        # Pack binding: store pack info if provided
        pack_bound = config.pack_source_path is not None

        # Materialize pack (snapshot copy semantics)
        materialization = await self._materialize_pack(config)

        # Generate Picoclaw config if we have runtime config
        materialized_config_path = None
        if config.runtime_bridge_config:
            self._generate_picoclaw_config(config)
            # In production, this would write to sandbox volume
            # For simulation, we track that config was "generated"
            materialized_config_path = materialization.get("config_path")

        # Fail-fast contract guard: dynamic paths must not be under pack mount
        if materialized_config_path and materialized_config_path.startswith(
            PACK_MOUNT_PATH
        ):
            raise SandboxConfigurationError(
                f"Config path must be outside pack mount {PACK_MOUNT_PATH}: {materialized_config_path}",
                provider_ref=ref,
                workspace_id=config.workspace_id,
            )

        # Start in HYDRATING state
        self._sandboxes[ref] = {
            "workspace_id": config.workspace_id,
            "state": SandboxState.HYDRATING,
            "health": SandboxHealth.UNKNOWN,
            "created_at": now,
            "last_activity_at": now,
            "config": config,
            "provider_state": "creating",
            "pack_bound": pack_bound,
            "pack_source_path": config.pack_source_path,
            "pack_digest": config.pack_digest,
            "materialized_config_path": materialized_config_path,
            "materialization": materialization,
        }

        # Create workspace symlinks for mount isolation parity (before READY)
        await self._create_workspace_symlinks(ref)

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
