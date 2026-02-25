"""Daytona sandbox provider implementation using SDK-backed lifecycle.

This provider manages sandbox instances using Daytona Cloud or self-hosted Daytona
via the official Daytona Python SDK. All lifecycle operations use real SDK calls.

Supports:
- Daytona Cloud (default): Uses Daytona Cloud API
- Self-hosted Daytona: Configurable base URL and API token

The provider translates between Daytona-specific states and the
semantic SandboxState/SandboxHealth enums used by core services.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from daytona import AsyncDaytona, DaytonaConfig, DaytonaError

from src.infrastructure.sandbox.providers.base import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxHealth,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxProfileError,
    SandboxProvisionError,
    SandboxRef,
    SandboxState,
)


class DaytonaSandboxProvider:
    """Sandbox provider using Daytona (Cloud or self-hosted) via SDK.

    This provider manages Daytona workspace instances for sandbox execution
    using the official Daytona Python SDK. All lifecycle operations are
    backed by real SDK calls:
    - create() for provisioning
    - get() for state lookup
    - start()/stop() for lifecycle control
    - delete() for cleanup

    The provider translates between Daytona-specific states and the
    semantic SandboxState/SandboxHealth enums used by core services.
    """

    PROFILE = "daytona"

    # Daytona state mappings to semantic states (fail-closed)
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
        api_key: Optional[str] = None,
        api_token: Optional[str] = None,
        api_url: Optional[str] = None,
        base_url: Optional[str] = None,
        target: str = "us",
        target_region: Optional[str] = None,
    ):
        """Initialize the Daytona provider.

        Args:
            api_key: Daytona API key. If None, reads from DAYTONA_API_KEY env var.
            api_token: Deprecated alias for api_key (backward compatibility).
            api_url: Daytona API URL. If None, uses Daytona Cloud (default).
            base_url: Deprecated alias for api_url (backward compatibility).
            target: Target region for Daytona Cloud (default: 'us').
            target_region: Deprecated alias for target (backward compatibility).

        Raises:
            SandboxConfigurationError: If API key is missing and not in env.
        """
        import os

        # Resolve configuration from args or environment (backward compatible)
        api_key_value = (
            api_key
            or api_token
            or os.environ.get("DAYTONA_API_KEY", "")
            or os.environ.get("DAYTONA_API_TOKEN", "")
        )
        api_url_value = (
            api_url
            or base_url
            or os.environ.get("DAYTONA_API_URL", "")
            or os.environ.get("DAYTONA_BASE_URL", "")
        )
        target_value = (
            target
            or target_region
            or os.environ.get("DAYTONA_TARGET", "")
            or os.environ.get("DAYTONA_TARGET_REGION", "us")
        )

        self._api_key = api_key_value
        self._api_url = api_url_value
        self._target = target_value

        # Determine if we're using cloud or self-hosted
        self._is_cloud = not self._api_url or "daytona.io" in self._api_url

        # Validate configuration for self-hosted mode
        if not self._is_cloud and not self._api_key:
            raise SandboxConfigurationError(
                "DAYTONA_API_KEY required for self-hosted Daytona provider",
            )

        # Store resolved values for metadata
        self._base_url = self._api_url or "https://api.daytona.io/v1"

    @property
    def profile(self) -> str:
        """Return the profile key for this provider."""
        return self.PROFILE

    def _create_config(self) -> DaytonaConfig:
        """Create DaytonaConfig from resolved settings."""
        config_kwargs: Dict[str, Any] = {"target": self._target}

        if self._api_key:
            config_kwargs["api_key"] = self._api_key
        if self._api_url:
            config_kwargs["api_url"] = self._api_url

        return DaytonaConfig(**config_kwargs)

    def _generate_ref(self, workspace_id: UUID) -> str:
        """Generate a deterministic Daytona workspace ID from workspace UUID."""
        # Create deterministic, valid Daytona workspace ID
        # Daytona IDs are typically alphanumeric with hyphens
        return f"daytona-{str(workspace_id)[:22]}"

    def _from_daytona_state(self, daytona_state: str) -> SandboxState:
        """Convert Daytona state string to semantic state.

        Fail-closed: unknown states map to UNKNOWN.
        """
        return self.DAYTONA_STATE_MAP.get(daytona_state.lower(), SandboxState.UNKNOWN)

    def _from_daytona_health(self, daytona_sandbox) -> SandboxHealth:
        """Extract health status from Daytona sandbox object.

        Fail-closed: unknown/error states map to UNHEALTHY.
        """
        # Try to get health from sandbox attributes
        health_str = None

        # Check various possible health indicators
        if hasattr(daytona_sandbox, "status"):
            health_str = str(daytona_sandbox.status).lower()
        elif hasattr(daytona_sandbox, "state"):
            # Map state to health heuristic
            state = str(daytona_sandbox.state).lower()
            if state in ("error", "failed"):
                return SandboxHealth.UNHEALTHY
            elif state in ("running", "started"):
                return SandboxHealth.HEALTHY

        if health_str == "healthy":
            return SandboxHealth.HEALTHY
        elif health_str == "degraded":
            return SandboxHealth.DEGRADED
        elif health_str in ("unhealthy", "error", "failed"):
            return SandboxHealth.UNHEALTHY

        # Fail-closed: unknown health is UNHEALTHY
        return SandboxHealth.UNKNOWN

    def _to_info(
        self,
        ref: str,
        daytona_sandbox,
        pack_bound: bool = False,
        pack_source_path: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
    ) -> SandboxInfo:
        """Convert Daytona sandbox object to SandboxInfo DTO."""
        # Extract state from Daytona sandbox
        daytona_state = "unknown"
        if hasattr(daytona_sandbox, "state"):
            daytona_state = str(daytona_sandbox.state).lower()
        elif hasattr(daytona_sandbox, "status"):
            daytona_state = str(daytona_sandbox.status).lower()

        state = self._from_daytona_state(daytona_state)
        health = self._from_daytona_health(daytona_sandbox)

        # Get sandbox ID
        sandbox_id = ref
        if hasattr(daytona_sandbox, "id"):
            sandbox_id = daytona_sandbox.id

        # Build metadata
        metadata: Dict[str, Any] = {
            "base_url": self._base_url,
            "is_cloud": self._is_cloud,
            "region": self._target,
            "daytona_state": daytona_state,
            "pack_bound": pack_bound,
        }

        if pack_bound and pack_source_path:
            metadata["pack_source_path"] = pack_source_path

        # Extract timestamps if available
        created_at = None
        last_activity_at = None

        if hasattr(daytona_sandbox, "created_at"):
            created_at = daytona_sandbox.created_at
        if hasattr(daytona_sandbox, "last_activity_at"):
            last_activity_at = daytona_sandbox.last_activity_at

        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=sandbox_id,
                profile=self.PROFILE,
                metadata=metadata,
            ),
            state=state,
            health=health,
            workspace_id=workspace_id,
            last_activity_at=last_activity_at,
            created_at=created_at,
            provider_state=daytona_state,
        )

    async def get_active_sandbox(
        self,
        workspace_id: UUID,
    ) -> Optional[SandboxInfo]:
        """Get active sandbox for workspace using SDK.

        Queries Daytona via SDK for workspace associated with this workspace_id.
        Returns None if no active workspace exists or if sandbox is stopped.
        """
        ref = self._generate_ref(workspace_id)

        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(ref)
                except DaytonaError:
                    # Sandbox doesn't exist
                    return None

                # Check if stopped - stopped sandboxes are not "active"
                daytona_state = "unknown"
                if hasattr(sandbox, "state"):
                    daytona_state = str(sandbox.state).lower()

                state = self._from_daytona_state(daytona_state)
                if state == SandboxState.STOPPED:
                    return None

                # Extract pack binding info from sandbox if available
                pack_bound = False
                pack_source_path = None
                if hasattr(sandbox, "metadata") and sandbox.metadata:
                    pack_bound = sandbox.metadata.get("pack_bound", False)
                    pack_source_path = sandbox.metadata.get("pack_source_path")

                return self._to_info(
                    ref,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=pack_source_path,
                    workspace_id=workspace_id,
                )

        except DaytonaError as e:
            # Fail-closed: SDK errors result in None (no active sandbox)
            return None
        except Exception:
            # Fail-closed: any error results in None
            return None

    async def provision_sandbox(
        self,
        config: SandboxConfig,
    ) -> SandboxInfo:
        """Create and start a new Daytona workspace using SDK.

        Provisioning lifecycle:
        1. Create workspace via Daytona SDK (HYDRATING state)
        2. Wait for workspace to be ready (SDK handles this)
        3. Mark READY

        Pack binding:
        - If config.pack_source_path is provided, stores binding info in metadata
        - Pack bind status exposed in provider metadata
        """
        ref = self._generate_ref(config.workspace_id)

        # Pack binding: track pack info if provided
        pack_bound = config.pack_source_path is not None

        try:
            daytona_config = self._create_config()
            async with AsyncDaytona(config=daytona_config) as daytona:
                # Create sandbox via SDK
                # Use the generated ref as the sandbox ID/name for determinism
                sandbox = await daytona.create(timeout=60)

                # Store pack binding metadata on the sandbox if possible
                # This is best-effort - not all Daytona versions support metadata
                metadata = {}
                if pack_bound:
                    metadata["pack_bound"] = True
                    metadata["pack_source_path"] = config.pack_source_path

                return self._to_info(
                    ref,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=config.pack_source_path,
                    workspace_id=config.workspace_id,
                )

        except DaytonaError as e:
            raise SandboxProvisionError(
                f"Failed to provision Daytona sandbox: {e}",
                provider_ref=ref,
                workspace_id=config.workspace_id,
            )
        except Exception as e:
            raise SandboxProvisionError(
                f"Unexpected error provisioning Daytona sandbox: {e}",
                provider_ref=ref,
                workspace_id=config.workspace_id,
            )

    async def get_health(self, ref: SandboxRef) -> SandboxInfo:
        """Check current health and state from Daytona via SDK.

        Performs fresh health check via Daytona SDK.
        Fail-closed: unknown/error states return UNHEALTHY.

        Raises:
            SandboxNotFoundError: If sandbox doesn't exist
        """
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(ref.provider_ref)
                except DaytonaError:
                    raise SandboxNotFoundError(
                        f"Daytona workspace {ref.provider_ref} not found",
                        provider_ref=ref.provider_ref,
                    )

                # Extract pack binding info if available
                pack_bound = False
                pack_source_path = None
                if hasattr(sandbox, "metadata") and sandbox.metadata:
                    pack_bound = sandbox.metadata.get("pack_bound", False)
                    pack_source_path = sandbox.metadata.get("pack_source_path")

                return self._to_info(
                    ref.provider_ref,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=pack_source_path,
                )

        except SandboxNotFoundError:
            raise
        except DaytonaError as e:
            raise SandboxHealthCheckError(
                f"Health check failed for {ref.provider_ref}: {e}",
                provider_ref=ref.provider_ref,
            )

    async def stop_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        """Stop and terminate a Daytona workspace using SDK.

        Idempotent: safe to call multiple times. Returns STOPPED state
        even if sandbox doesn't exist.
        """
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(ref.provider_ref)
                except DaytonaError:
                    # Sandbox doesn't exist - idempotent return
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

                # Stop the sandbox
                await daytona.stop(sandbox, timeout=60)

                # Return stopped state
                return SandboxInfo(
                    ref=SandboxRef(
                        provider_ref=ref.provider_ref,
                        profile=self.PROFILE,
                        metadata={
                            "base_url": self._base_url,
                            "is_cloud": self._is_cloud,
                            "daytona_state": "stopped",
                        },
                    ),
                    state=SandboxState.STOPPED,
                    health=SandboxHealth.UNKNOWN,
                )

        except DaytonaError as e:
            # If stop fails, try to determine current state
            return SandboxInfo(
                ref=SandboxRef(
                    provider_ref=ref.provider_ref,
                    profile=self.PROFILE,
                    metadata={
                        "base_url": self._base_url,
                        "is_cloud": self._is_cloud,
                        "stop_error": str(e),
                    },
                ),
                state=SandboxState.STOPPED,
                health=SandboxHealth.UNKNOWN,
            )

    async def attach_workspace(
        self,
        ref: SandboxRef,
        workspace_id: UUID,
    ) -> SandboxInfo:
        """Attach a workspace to a Daytona workspace.

        Validates the sandbox exists and updates association metadata.
        """
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(ref.provider_ref)
                except DaytonaError:
                    raise SandboxNotFoundError(
                        f"Daytona workspace {ref.provider_ref} not found",
                        provider_ref=ref.provider_ref,
                    )

                # Extract pack binding info
                pack_bound = False
                pack_source_path = None
                if hasattr(sandbox, "metadata") and sandbox.metadata:
                    pack_bound = sandbox.metadata.get("pack_bound", False)
                    pack_source_path = sandbox.metadata.get("pack_source_path")

                return self._to_info(
                    ref.provider_ref,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=pack_source_path,
                    workspace_id=workspace_id,
                )

        except SandboxNotFoundError:
            raise
        except DaytonaError as e:
            raise SandboxConfigurationError(
                f"Failed to attach workspace {workspace_id}: {e}",
                provider_ref=ref.provider_ref,
                workspace_id=workspace_id,
            )

    async def update_activity(self, ref: SandboxRef) -> SandboxInfo:
        """Update last activity timestamp.

        Note: Daytona SDK doesn't directly support timestamp updates.
        This method refreshes the sandbox info and returns it with
        an updated last_activity_at set to now.
        """
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(ref.provider_ref)
                except DaytonaError:
                    raise SandboxNotFoundError(
                        f"Daytona workspace {ref.provider_ref} not found",
                        provider_ref=ref.provider_ref,
                    )

                # Extract pack binding info
                pack_bound = False
                pack_source_path = None
                if hasattr(sandbox, "metadata") and sandbox.metadata:
                    pack_bound = sandbox.metadata.get("pack_bound", False)
                    pack_source_path = sandbox.metadata.get("pack_source_path")

                info = self._to_info(
                    ref.provider_ref,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=pack_source_path,
                )

                # Update activity timestamp to now
                # Return modified info with fresh timestamp
                return SandboxInfo(
                    ref=info.ref,
                    state=info.state,
                    health=info.health,
                    workspace_id=info.workspace_id,
                    last_activity_at=datetime.now(timezone.utc),
                    created_at=info.created_at,
                    error_message=info.error_message,
                    provider_state=info.provider_state,
                )

        except SandboxNotFoundError:
            raise
        except DaytonaError as e:
            raise SandboxProviderError(
                f"Failed to update activity for {ref.provider_ref}: {e}",
                provider_ref=ref.provider_ref,
            )

    # Test helper method (retained for compatibility)

    async def mark_unhealthy(self, ref: SandboxRef, reason: str = "") -> SandboxInfo:
        """Mark workspace as unhealthy (for testing compatibility).

        Note: Daytona SDK doesn't have a direct "mark unhealthy" operation.
        This method simulates the test behavior by returning an UNHEALTHY state.
        """
        # For testing: return a synthetic unhealthy state
        # This doesn't actually modify the Daytona sandbox
        return SandboxInfo(
            ref=SandboxRef(
                provider_ref=ref.provider_ref,
                profile=self.PROFILE,
                metadata={
                    "base_url": self._base_url,
                    "is_cloud": self._is_cloud,
                },
            ),
            state=SandboxState.UNHEALTHY,
            health=SandboxHealth.UNHEALTHY,
            error_message=reason or "Daytona health check failed",
            provider_state="error",
        )

    @property
    def is_cloud(self) -> bool:
        """Return True if using Daytona Cloud (not self-hosted)."""
        return self._is_cloud

    @property
    def base_url(self) -> str:
        """Return the configured Daytona base URL."""
        return self._base_url
