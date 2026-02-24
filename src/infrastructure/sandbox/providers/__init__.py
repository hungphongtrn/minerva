"""Sandbox provider implementations.

Provides stable exports for provider classes and factory functions
used by acceptance tests and portability verification.
"""

from src.infrastructure.sandbox.providers.base import (
    SandboxConfigurationError,
    SandboxHealth,
    SandboxNotFoundError,
    SandboxProvisionError,
    SandboxHealthCheckError,
    SandboxProfileError,
    SandboxProvider,
    SandboxProviderError,
    SandboxRef,
    SandboxState,
    SandboxInfo,
    SandboxConfig,
)
from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
from src.infrastructure.sandbox.providers.local_compose import (
    LocalComposeSandboxProvider,
)
from src.infrastructure.sandbox.providers.factory import (
    get_provider,
    list_available_profiles,
    get_current_profile,
    register_provider,
)

__all__ = [
    # Base types and protocols
    "SandboxProvider",
    "SandboxState",
    "SandboxHealth",
    "SandboxRef",
    "SandboxInfo",
    "SandboxConfig",
    # Errors
    "SandboxProviderError",
    "SandboxConfigurationError",
    "SandboxProfileError",
    "SandboxNotFoundError",
    "SandboxProvisionError",
    "SandboxHealthCheckError",
    # Provider implementations
    "DaytonaSandboxProvider",
    "LocalComposeSandboxProvider",
    # Factory functions
    "get_provider",
    "list_available_profiles",
    "get_current_profile",
    "register_provider",
]
