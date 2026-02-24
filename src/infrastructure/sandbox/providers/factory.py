"""Provider factory for sandbox adapter instantiation.

This module provides factory functions to instantiate the appropriate
sandbox provider based on configuration settings. Services use the factory
to obtain provider instances without hardcoding provider selection logic.
"""

from typing import Dict, Type

from src.config.settings import settings
from src.infrastructure.sandbox.providers.base import (
    SandboxConfigurationError,
    SandboxProfileError,
    SandboxProvider,
)
from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider
from src.infrastructure.sandbox.providers.local_compose import (
    LocalComposeSandboxProvider,
)


# Registry of available provider implementations
_PROVIDER_REGISTRY: Dict[str, Type[SandboxProvider]] = {
    "local_compose": LocalComposeSandboxProvider,
    "daytona": DaytonaSandboxProvider,
}


def get_provider(profile: str | None = None) -> SandboxProvider:
    """Get a sandbox provider instance for the specified profile.

    If no profile is specified, uses the SANDBOX_PROFILE setting.

    Args:
        profile: Provider profile key ('local_compose' or 'daytona').
                If None, reads from settings.SANDBOX_PROFILE.

    Returns:
        Configured SandboxProvider instance.

    Raises:
        SandboxProfileError: If the profile is unsupported or invalid.
        SandboxConfigurationError: If provider configuration is missing/invalid.

    Example:
        # Get provider from settings
        provider = get_provider()

        # Get specific provider
        provider = get_provider("daytona")
    """
    # Handle explicit empty string vs None
    if profile is not None:
        profile_key = profile
    else:
        profile_key = settings.SANDBOX_PROFILE

    if not profile_key or not profile_key.strip():
        raise SandboxProfileError(
            "No sandbox profile specified. "
            "Set SANDBOX_PROFILE environment variable or pass profile argument."
        )

    profile_key = profile_key.lower().strip()

    if profile_key not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise SandboxProfileError(
            f"Unsupported sandbox profile: '{profile_key}'. "
            f"Available profiles: {available}"
        )

    provider_class = _PROVIDER_REGISTRY[profile_key]

    # Instantiate with profile-specific configuration
    if profile_key == "local_compose":
        return _create_local_compose_provider()
    elif profile_key == "daytona":
        return _create_daytona_provider()
    else:
        # This should never happen due to the registry check above
        raise SandboxProfileError(
            f"Provider factory not implemented for: {profile_key}"
        )


def _create_local_compose_provider() -> LocalComposeSandboxProvider:
    """Create a LocalComposeSandboxProvider with configuration from settings."""
    # Local compose may optionally use a specific compose file path
    # For now, uses default docker-compose.yml
    return LocalComposeSandboxProvider()


def _create_daytona_provider() -> DaytonaSandboxProvider:
    """Create a DaytonaSandboxProvider with configuration from settings."""
    # Validate Daytona configuration
    if settings.SANDBOX_PROFILE == "daytona" and not settings.DAYTONA_API_TOKEN:
        raise SandboxConfigurationError(
            "DAYTONA_API_TOKEN is required when SANDBOX_PROFILE=daytona. "
            "Set the DAYTONA_API_TOKEN environment variable."
        )

    return DaytonaSandboxProvider(
        api_token=settings.DAYTONA_API_TOKEN or None,
        base_url=settings.DAYTONA_BASE_URL or None,
        target_region=settings.DAYTONA_TARGET_REGION,
    )


def list_available_profiles() -> list[str]:
    """Return a list of available sandbox provider profile keys.

    Returns:
        Sorted list of supported profile names.
    """
    return sorted(_PROVIDER_REGISTRY.keys())


def register_provider(profile: str, provider_class: Type[SandboxProvider]) -> None:
    """Register a custom provider implementation.

    This allows extending the system with additional sandbox providers
    without modifying the factory code.

    Args:
        profile: Profile key for the provider.
        provider_class: Provider class implementing SandboxProvider.

    Raises:
        ValueError: If profile key is invalid or class doesn't implement
                   the SandboxProvider interface.

    Example:
        register_provider("kubernetes", KubernetesSandboxProvider)
    """
    if not profile or not isinstance(profile, str):
        raise ValueError("Profile key must be a non-empty string")

    if not issubclass(provider_class, SandboxProvider):
        raise ValueError(
            f"Provider class must implement SandboxProvider interface: {provider_class}"
        )

    _PROVIDER_REGISTRY[profile.lower().strip()] = provider_class


def get_current_profile() -> str:
    """Get the currently configured sandbox profile from settings.

    Returns:
        The SANDBOX_PROFILE setting value.
    """
    return settings.SANDBOX_PROFILE
