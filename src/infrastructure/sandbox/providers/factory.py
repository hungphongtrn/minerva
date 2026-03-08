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
            f"Unsupported sandbox profile: '{profile_key}'. Available profiles: {available}"
        )

    _PROVIDER_REGISTRY[profile_key]

    # Instantiate with profile-specific configuration
    if profile_key == "local_compose":
        return _create_local_compose_provider()
    elif profile_key == "daytona":
        return _create_daytona_provider()
    else:
        # This should never happen due to the registry check above
        raise SandboxProfileError(f"Provider factory not implemented for: {profile_key}")


def _create_local_compose_provider() -> LocalComposeSandboxProvider:
    """Create a LocalComposeSandboxProvider with configuration from settings."""
    # Local compose may optionally use a specific compose file path
    # For now, uses default docker-compose.yml
    return LocalComposeSandboxProvider()


def _create_daytona_provider() -> DaytonaSandboxProvider:
    """Create a DaytonaSandboxProvider with configuration from settings.

    Validates SDK configuration and fails closed if credentials are missing
    for non-cloud deployments.
    """
    # Resolve API key from new or legacy settings
    api_key = settings.DAYTONA_API_KEY or settings.DAYTONA_API_TOKEN or None

    # Validate Daytona configuration for self-hosted mode
    if settings.SANDBOX_PROFILE == "daytona":
        # Check if we're in self-hosted mode (has custom API URL)
        api_url = settings.DAYTONA_API_URL or settings.DAYTONA_BASE_URL or None
        is_cloud = not api_url or "daytona.io" in api_url

        if not is_cloud and not api_key:
            raise SandboxConfigurationError(
                "DAYTONA_API_KEY is required for self-hosted Daytona. "
                "Set DAYTONA_API_KEY environment variable or use Daytona Cloud."
            )

    # Resolve target region
    target = settings.DAYTONA_TARGET or settings.DAYTONA_TARGET_REGION or "us"

    # Resolve image contract settings - filter out MagicMock from test mocks
    strict_mode = getattr(settings, "DAYTONA_BASE_IMAGE_STRICT_MODE", False)
    if strict_mode is not None and not isinstance(strict_mode, bool):
        strict_mode = False

    digest_required = getattr(settings, "DAYTONA_BASE_IMAGE_DIGEST_REQUIRED", False)
    if digest_required is not None and not isinstance(digest_required, bool):
        digest_required = False

    auto_stop_interval = getattr(settings, "DAYTONA_AUTO_STOP_INTERVAL", 0)
    if auto_stop_interval is not None and not isinstance(auto_stop_interval, int):
        auto_stop_interval = 0

    snapshot_name = getattr(settings, "DAYTONA_PICOCLAW_SNAPSHOT_NAME", None)
    if snapshot_name is not None and not isinstance(snapshot_name, str):
        snapshot_name = None
    if isinstance(snapshot_name, str) and not snapshot_name.strip():
        snapshot_name = None
    if isinstance(snapshot_name, str):
        normalized_snapshot = snapshot_name.strip().lower()
        if normalized_snapshot in {"picoclaw-base", "picoclaw-snapshot"}:
            snapshot_name = "zeroclaw-base"

    # Resolve base image - filter out MagicMock from test mocks
    base_image = getattr(settings, "DAYTONA_BASE_IMAGE", None)
    if base_image is not None and not isinstance(base_image, str):
        base_image = None

    return DaytonaSandboxProvider(
        api_key=api_key,
        api_url=settings.DAYTONA_API_URL or None,
        base_url=settings.DAYTONA_BASE_URL or None,
        target=target,
        target_region=settings.DAYTONA_TARGET_REGION or None,
        base_image=base_image,
        auto_stop_interval=auto_stop_interval,
        snapshot_name=snapshot_name,
        strict_mode=strict_mode,
        digest_required=digest_required,
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
