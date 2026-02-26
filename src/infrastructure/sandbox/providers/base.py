"""Provider protocol and shared semantic models for sandbox adapters.

This module defines the abstract interface and data structures used by
core services to interact with sandbox providers (local Docker Compose,
Daytona Cloud, etc.) without provider-specific branching.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional
from uuid import UUID


class SandboxState(Enum):
    """Semantic states for sandbox lifecycle management.

    These states are provider-agnostic and represent the canonical
    state machine that services use for routing decisions.
    """

    UNKNOWN = auto()  # State cannot be determined
    READY = auto()  # Active and healthy, ready for use
    HYDRATING = auto()  # Being created or restored from checkpoint
    RESTORING = auto()  # Actively restoring from checkpoint
    UNHEALTHY = auto()  # Active but failed health checks
    STOPPED = auto()  # Stopped or terminated
    STOPPING = auto()  # In the process of stopping


class SandboxHealth(Enum):
    """Health status for sandbox instances.

    Independent of state - a sandbox can be READY but UNHEALTHY
    if health checks are failing.
    """

    UNKNOWN = auto()  # Health status not yet determined
    HEALTHY = auto()  # All health checks passing
    DEGRADED = auto()  # Some checks failing but functional
    UNHEALTHY = auto()  # Critical health checks failing


@dataclass(frozen=True)
class SandboxRef:
    """Provider-agnostic reference to a sandbox instance.

    Services use this reference to route operations to specific
    sandbox instances without knowing provider internals.
    """

    provider_ref: str
    """Provider-specific identifier (e.g., container ID, Daytona workspace ID)."""

    profile: str
    """Profile key identifying the provider type (e.g., 'local_compose', 'daytona')."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Provider-specific metadata for debugging/observability."""


@dataclass(frozen=True)
class SandboxInfo:
    """Complete snapshot of sandbox state and health.

    This is the primary DTO returned by provider operations.
    Services use this for routing decisions, health checks,
    and lifecycle management.
    """

    ref: SandboxRef
    """Reference to the sandbox instance."""

    state: SandboxState
    """Current semantic state."""

    health: SandboxHealth
    """Current health status."""

    workspace_id: Optional[UUID] = None
    """Associated workspace if attached."""

    last_activity_at: Optional[datetime] = None
    """Timestamp of last routed activity (for TTL calculations)."""

    created_at: Optional[datetime] = None
    """When the sandbox was first created."""

    error_message: Optional[str] = None
    """Human-readable error if state is UNHEALTHY or terminal failure."""

    provider_state: Optional[str] = None
    """Provider-native state string for debugging."""


@dataclass(frozen=True)
class SandboxConfig:
    """Configuration for sandbox provisioning.

    Services pass this to providers when creating new sandboxes.
    Providers extract profile-specific settings from this config.
    """

    workspace_id: UUID
    """Workspace to attach to the sandbox."""

    idle_ttl_seconds: int = 3600
    """Time-to-live in seconds before auto-stop on idle."""

    env_vars: Dict[str, str] = field(default_factory=dict)
    """Environment variables to inject into the sandbox."""

    resource_limits: Optional[Dict[str, Any]] = None
    """Resource constraints (CPU, memory, etc.)."""

    pack_source_path: Optional[str] = None
    """Path to agent pack source for mounting/copying."""

    pack_digest: Optional[str] = None
    """SHA-256 digest of the agent pack at provisioning time for stale detection."""

    runtime_bridge_config: Optional[Dict[str, Any]] = None
    """Runtime bridge configuration for Picoclaw gateway (model, channels, etc.)."""


class SandboxProviderError(Exception):
    """Base exception for sandbox provider failures."""

    def __init__(
        self,
        message: str,
        provider_ref: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
    ):
        super().__init__(message)
        self.provider_ref = provider_ref
        self.workspace_id = workspace_id


class SandboxNotFoundError(SandboxProviderError):
    """Raised when a referenced sandbox cannot be found."""

    pass


class SandboxProvisionError(SandboxProviderError):
    """Raised when sandbox provisioning fails."""

    pass


class SandboxHealthCheckError(SandboxProviderError):
    """Raised when health check fails irrecoverably."""

    pass


class SandboxConfigurationError(SandboxProviderError):
    """Raised when provider configuration is invalid or missing."""

    pass


class SandboxProfileError(SandboxConfigurationError):
    """Raised when an unsupported or invalid profile is requested."""

    pass


class SandboxProvider(ABC):
    """Abstract interface for sandbox providers.

    All provider implementations (local Docker Compose, Daytona, etc.)
    must satisfy this contract. Services depend only on this interface,
    ensuring provider-agnostic routing and lifecycle management.

    The contract guarantees:
    - Semantic state consistency across all providers
    - Idempotent stop operations
    - Fail-closed behavior for unknown/error states
    """

    @property
    @abstractmethod
    def profile(self) -> str:
        """Return the profile key for this provider (e.g., 'local_compose')."""
        pass

    @abstractmethod
    async def get_active_sandbox(
        self,
        workspace_id: UUID,
    ) -> Optional[SandboxInfo]:
        """Get the active sandbox for a workspace if one exists.

        Returns None if no active sandbox exists for the workspace.
        Returns sandbox info with current state/health if one exists.

        Args:
            workspace_id: Workspace to look up

        Returns:
            SandboxInfo if active sandbox exists, None otherwise

        Raises:
            SandboxProviderError: On provider communication failures
        """
        pass

    @abstractmethod
    async def provision_sandbox(
        self,
        config: SandboxConfig,
    ) -> SandboxInfo:
        """Create and start a new sandbox for the workspace.

        The sandbox may be created fresh or restored from a checkpoint
        depending on provider capabilities and configuration.

        Args:
            config: Sandbox configuration including workspace ID

        Returns:
            SandboxInfo for the newly provisioned sandbox

        Raises:
            SandboxProvisionError: If provisioning fails
            SandboxConfigurationError: If config is invalid
        """
        pass

    @abstractmethod
    async def get_health(
        self,
        ref: SandboxRef,
    ) -> SandboxInfo:
        """Check current health and state of a sandbox.

        Performs a fresh health check and returns updated state.
        This is used by routing to verify sandbox health before use.

        Args:
            ref: Reference to the sandbox to check

        Returns:
            Updated SandboxInfo with current state and health

        Raises:
            SandboxNotFoundError: If sandbox no longer exists
            SandboxHealthCheckError: On health check failures
        """
        pass

    @abstractmethod
    async def stop_sandbox(
        self,
        ref: SandboxRef,
    ) -> SandboxInfo:
        """Stop and terminate a sandbox.

        This operation is idempotent - calling it multiple times
        on the same sandbox is safe and returns consistent state.

        Args:
            ref: Reference to the sandbox to stop

        Returns:
            SandboxInfo with final STOPPED state

        Raises:
            SandboxNotFoundError: If sandbox doesn't exist (idempotent)
            SandboxProviderError: On stop failures
        """
        pass

    @abstractmethod
    async def attach_workspace(
        self,
        ref: SandboxRef,
        workspace_id: UUID,
    ) -> SandboxInfo:
        """Attach a workspace to an existing sandbox.

        Used when hydrating a sandbox from checkpoint or when
        reattaching to an existing sandbox.

        Args:
            ref: Reference to the sandbox
            workspace_id: Workspace to attach

        Returns:
            Updated SandboxInfo with workspace attached

        Raises:
            SandboxNotFoundError: If sandbox doesn't exist
            SandboxProviderError: On attachment failures
        """
        pass

    @abstractmethod
    async def update_activity(
        self,
        ref: SandboxRef,
    ) -> SandboxInfo:
        """Update last_activity timestamp for TTL tracking.

        Called by routing layer when sandbox is used.

        Args:
            ref: Reference to the sandbox

        Returns:
            Updated SandboxInfo with refreshed activity timestamp

        Raises:
            SandboxNotFoundError: If sandbox doesn't exist
        """
        pass
