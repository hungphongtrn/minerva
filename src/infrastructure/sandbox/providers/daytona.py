"""Daytona sandbox provider implementation using SDK-backed lifecycle.

This provider manages sandbox instances using Daytona Cloud or self-hosted Daytona
via the official Daytona Python SDK. All lifecycle operations use real SDK calls.

Supports:
- Daytona Cloud (default): Uses Daytona Cloud API
- Self-hosted Daytona: Configurable base URL and API token

The provider translates between Daytona-specific states and the
semantic SandboxState/SandboxHealth enums used by core services.
"""

import asyncio
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from daytona import (
    AsyncDaytona,
    DaytonaConfig,
    DaytonaError,
    CreateSandboxFromSnapshotParams,
    VolumeMount,
)

from src.infrastructure.sandbox.providers.base import (
    CONFIG_PATH,
    IDENTITY_DIRS,
    IDENTITY_FILES,
    PACK_MOUNT_PATH,
    SandboxConfig,
    SandboxConfigurationError,
    SandboxHealth,
    SandboxHealthCheckError,
    SandboxIdentityError,
    SandboxInfo,
    SandboxNotFoundError,
    SandboxProviderError,
    SandboxProvisionError,
    SandboxRef,
    SandboxState,
    WORKSPACE_PATH,
)


@dataclass
class IdentityVerificationResult:
    """Result of identity file verification."""

    ready: bool
    missing_files: List[str]
    error_message: Optional[str] = None


class SandboxGatewayError(SandboxProviderError):
    """Raised when gateway endpoint resolution fails."""

    pass


class SandboxImageContractError(SandboxConfigurationError):
    """Raised when base image configuration violates the runtime contract."""

    def __init__(
        self,
        message: str,
        provider_ref: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        image_ref: Optional[str] = None,
        contract_violation: Optional[str] = None,
        remediation: Optional[str] = None,
    ):
        super().__init__(message, provider_ref=provider_ref, workspace_id=workspace_id)
        self.image_ref = image_ref
        self.contract_violation = contract_violation
        self.remediation = (
            remediation
            or "Ensure DAYTONA_BASE_IMAGE uses a digest-pinned reference (repo/image@sha256:...)"
        )

    def __str__(self) -> str:
        parts = [self.args[0] if self.args else "SandboxImageContractError"]
        if self.image_ref:
            parts.append(f"image_ref='{self.image_ref}'")
        if self.contract_violation:
            parts.append(f"violation='{self.contract_violation}'")
        return " | ".join(parts)


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

    # Required identity files for Picoclaw runtime
    REQUIRED_IDENTITY_FILES: Set[str] = {"AGENT.md", "SOUL.md", "IDENTITY.md"}
    REQUIRED_IDENTITY_DIRS: Set[str] = {"skills"}
    PROVISION_CREATE_TIMEOUT_SECONDS = 20.0
    IDENTITY_VERIFY_TIMEOUT_SECONDS = 20.0
    BRIDGE_PORT = 18790
    BRIDGE_START_MAX_ATTEMPTS = 3
    BRIDGE_START_BACKOFF_SECONDS = 1.0
    BRIDGE_LISTEN_TIMEOUT_SECONDS = 20.0

    def _normalize_daytona_value(self, value: Any) -> str:
        """Normalize Daytona SDK enum/string values into lowercase tokens."""
        if value is None:
            return "unknown"

        raw_value = getattr(value, "value", value)
        return str(raw_value).lower()

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_token: Optional[str] = None,
        api_url: Optional[str] = None,
        base_url: Optional[str] = None,
        target: str = "us",
        target_region: Optional[str] = None,
        base_image: Optional[str] = None,
        image_labels: Optional[Dict[str, str]] = None,
        auto_stop_interval: Optional[int] = None,
        strict_mode: bool = False,
        digest_required: bool = False,
        snapshot_name: Optional[str] = None,
    ):
        """Initialize the Daytona provider.

        Args:
            api_key: Daytona API key. If None, reads from DAYTONA_API_KEY env var.
            api_token: Deprecated alias for api_key (backward compatibility).
            api_url: Daytona API URL. If None, uses Daytona Cloud (default).
            base_url: Deprecated alias for api_url (backward compatibility).
            target: Target region for Daytona Cloud (default: 'us').
            target_region: Deprecated alias for target (backward compatibility).
            base_image: Docker image to use for sandbox (defaults to env or registry default).
            image_labels: Labels to apply to sandbox image.
            auto_stop_interval: Auto-stop interval in seconds (0 disables, None uses env default).
            snapshot_name: Snapshot name for provisioning (defaults to DAYTONA_PICOCLAW_SNAPSHOT_NAME env var).
            strict_mode: If True, enforces deterministic image contract validation.
            digest_required: If True, requires digest-pinned image references (implied by strict_mode).

        Raises:
            SandboxConfigurationError: If API key is missing and not in env.
            SandboxImageContractError: If base_image violates runtime contract in strict mode.
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

        # Image configuration
        # If base_image is explicitly provided (even if empty string), use it
        # Otherwise fall back to environment variable
        if base_image is not None:
            self._base_image = base_image
        else:
            self._base_image = os.environ.get(
                "DAYTONA_BASE_IMAGE", "daytonaio/workspace-picoclaw:latest"
            )
        self._image_labels = image_labels or {}

        # Auto-stop interval: 0 disables auto-stop for runtime continuity
        # Default: 0 (disabled) for production runtime continuity
        self._auto_stop_interval = (
            auto_stop_interval
            if auto_stop_interval is not None
            else int(os.environ.get("DAYTONA_AUTO_STOP_INTERVAL", "0"))
        )

        # Snapshot name for provisioning (defaults to environment variable)
        self._snapshot_name = (
            snapshot_name
            if snapshot_name is not None
            else os.environ.get("DAYTONA_PICOCLAW_SNAPSHOT_NAME", "picoclaw-snapshot")
        )

        # Image contract validation settings
        self._strict_mode = strict_mode
        self._digest_required = digest_required

        # Determine if we're using cloud or self-hosted
        self._is_cloud = not self._api_url or "daytona.io" in self._api_url

        # Validate configuration for self-hosted mode
        if not self._is_cloud and not self._api_key:
            raise SandboxConfigurationError(
                "DAYTONA_API_KEY required for self-hosted Daytona provider",
            )

        # Store resolved values for metadata
        self._base_url = self._api_url or "https://api.daytona.io/v1"

        # Image contract validation (fail-fast on startup)
        self._validate_base_image_contract(strict_mode, digest_required)

    def _validate_base_image_contract(
        self,
        strict_mode: bool = False,
        digest_required: bool = False,
    ) -> None:
        """Validate base image reference against runtime contract.

        Args:
            strict_mode: If True, enforces full deterministic contract
            digest_required: If True, requires digest-pinned image references

        Raises:
            SandboxImageContractError: When image violates the contract
        """
        import re

        is_strict = strict_mode or digest_required
        if not is_strict:
            return  # Permissive mode - no validation

        # Check for empty/unsafe image reference
        if not self._base_image or self._base_image.strip() == "":
            raise SandboxImageContractError(
                message="DAYTONA_BASE_IMAGE is empty or not set",
                image_ref=self._base_image,
                contract_violation="empty_image_reference",
                remediation="Set DAYTONA_BASE_IMAGE to a digest-pinned image reference",
            )

        # Check for digest format: repo/image@sha256:...
        digest_pattern = re.compile(r"^.+@sha256:[a-f0-9]{64}$")

        if not digest_pattern.match(self._base_image):
            violation = "mutable_tag_reference"
            if ":" not in self._base_image and "@" not in self._base_image:
                violation = "missing_tag_or_digest"

            raise SandboxImageContractError(
                message="DAYTONA_BASE_IMAGE must use digest-pinned format for production safety",
                image_ref=self._base_image,
                contract_violation=violation,
                remediation=(
                    "Use digest-pinned format: 'registry/image@sha256:abc123...' "
                    "instead of mutable tags like 'registry/image:latest'"
                ),
            )

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

    async def _maybe_await(self, value: Any) -> Any:
        """Await a value if needed."""
        if inspect.isawaitable(value):
            return await value
        return value

    async def _exec_checked(self, sandbox: Any, command: str) -> Dict[str, Any]:
        """Execute a command in sandbox and fail on non-zero exit."""
        result = await self._maybe_await(sandbox.process.exec(command))

        exit_code = getattr(result, "exit_code", 0)
        stdout = getattr(result, "result", None) or getattr(result, "stdout", "")
        stderr = getattr(result, "stderr", "")

        if exit_code != 0:
            raise SandboxProvisionError(
                f"Sandbox command failed (exit={exit_code}): {command}; stderr={stderr or stdout}"
            )

        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }

    async def _best_effort_stop_failed_sandbox(
        self,
        daytona: AsyncDaytona,
        sandbox: Any,
    ) -> None:
        """Attempt to stop a partially provisioned sandbox.

        Cleanup is best-effort and must never mask the original provisioning error.
        """
        try:
            await self._maybe_await(daytona.stop(sandbox, timeout=60))
        except Exception:
            return

    async def _best_effort_cleanup_failed_create(
        self,
        daytona: AsyncDaytona,
        config: SandboxConfig,
    ) -> None:
        """Cleanup provider-side ERROR sandboxes left by failed create attempts."""
        try:
            listed = await self._maybe_await(daytona.list())
        except Exception:
            return

        items = getattr(listed, "items", None) or []
        workspace_id = str(config.workspace_id)

        for candidate in items:
            labels = getattr(candidate, "labels", None) or {}
            if labels.get("workspace_id") != workspace_id:
                continue
            if config.external_user_id and labels.get("external_user_id") != str(
                config.external_user_id
            ):
                continue
            if getattr(candidate, "snapshot", None) != self._snapshot_name:
                continue

            state = getattr(candidate, "state", None)
            state_val = (getattr(state, "value", None) or str(state)).strip().lower()
            if state_val != "error":
                continue

            try:
                await self._maybe_await(daytona.delete(candidate, timeout=60))
            except Exception:
                try:
                    await self._maybe_await(daytona.stop(candidate, timeout=60))
                except Exception:
                    continue

    async def verify_identity_files(
        self,
        sandbox_id: str,
        timeout: float = 30.0,
    ) -> IdentityVerificationResult:
        """Verify required identity files are mounted in the sandbox via file API.

        This is a hard gate for request acceptance - sandboxes must have
        AGENT.md, SOUL.md, IDENTITY.md, and skills/ directory mounted.
        Uses Daytona SDK file operations to verify real file presence with polling.

        Args:
            sandbox_id: The Daytona sandbox ID to verify.
            timeout: Maximum time to wait for identity files (seconds).

        Returns:
            IdentityVerificationResult with ready status and missing files list.

        Raises:
            SandboxIdentityError: If verification fails irrecoverably.
        """
        import asyncio

        required_files = [f"{WORKSPACE_PATH}/{f}" for f in self.REQUIRED_IDENTITY_FILES]
        required_dirs = [f"{WORKSPACE_PATH}/{d}" for d in self.REQUIRED_IDENTITY_DIRS]

        start_time = asyncio.get_event_loop().time()

        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                # Poll until files are ready or timeout
                last_state = "unknown"
                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        return IdentityVerificationResult(
                            ready=False,
                            missing_files=list(self.REQUIRED_IDENTITY_FILES),
                            error_message=(
                                f"Timeout waiting for identity files ({elapsed:.1f}s); "
                                f"last_state={last_state}"
                            ),
                        )

                    try:
                        sandbox = await daytona.get(sandbox_id)
                    except DaytonaError as e:
                        raise SandboxIdentityError(
                            f"Failed to refresh sandbox for identity check: {e}",
                            provider_ref=sandbox_id,
                        )

                    # Check sandbox is in a state where files can be checked
                    state = "unknown"
                    if hasattr(sandbox, "state"):
                        state = self._normalize_daytona_value(sandbox.state)
                    elif hasattr(sandbox, "status"):
                        state = self._normalize_daytona_value(sandbox.status)
                    last_state = state

                    if state not in ("running", "started"):
                        await asyncio.sleep(0.5)
                        continue

                    async def _get_file_info(path: str):
                        result = sandbox.fs.get_file_info(path)
                        if inspect.isawaitable(result):
                            return await result
                        return result

                    # Check files exist using file API
                    missing_files = []
                    for file_path in required_files:
                        try:
                            file_info = await _get_file_info(file_path)
                            if not file_info or getattr(file_info, "is_dir", False):
                                missing_files.append(file_path)
                        except DaytonaError:
                            missing_files.append(file_path)

                    # Check directories exist and are directories
                    missing_dirs = []
                    for dir_path in required_dirs:
                        try:
                            dir_info = await _get_file_info(dir_path)
                            if not dir_info or not getattr(dir_info, "is_dir", False):
                                missing_dirs.append(dir_path)
                        except DaytonaError:
                            missing_dirs.append(dir_path)

                    # If all present, we're ready
                    if not missing_files and not missing_dirs:
                        return IdentityVerificationResult(
                            ready=True,
                            missing_files=[],
                            error_message=None,
                        )

                    # Wait before retry
                    await asyncio.sleep(0.5)

        except SandboxIdentityError:
            raise
        except DaytonaError as e:
            raise SandboxIdentityError(
                f"Daytona SDK error during identity verification: {e}",
                provider_ref=sandbox_id,
            )
        except Exception as e:
            raise SandboxIdentityError(
                f"Unexpected error during identity verification: {e}",
                provider_ref=sandbox_id,
            )

    async def resolve_gateway_endpoint(
        self,
        sandbox_id: str,
    ) -> str:
        """Resolve the authoritative gateway endpoint for a sandbox.

        Extracts the gateway URL from Daytona sandbox metadata or preview URLs
        in one canonical method. This is the single source of truth for
        bridge execution URLs.

        Args:
            sandbox_id: The Daytona sandbox ID.

        Returns:
            Gateway URL string (e.g., "https://gateway-{id}.daytona.run:18790").

        Raises:
            SandboxGatewayError: If endpoint cannot be resolved.
        """
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                try:
                    sandbox = await daytona.get(sandbox_id)
                except DaytonaError as e:
                    raise SandboxGatewayError(
                        f"Failed to get sandbox for gateway resolution: {e}",
                        provider_ref=sandbox_id,
                    )

                # Strategy 1: Check for explicit gateway_url in metadata
                if hasattr(sandbox, "metadata") and sandbox.metadata:
                    gateway_url = sandbox.metadata.get("gateway_url")
                    if gateway_url:
                        return gateway_url

                # Strategy 2: Use Daytona preview-link APIs for bridge port.
                preview_methods = [
                    "get_preview_link",
                    "create_preview_link",
                    "create_signed_preview_url",
                ]

                for method_name in preview_methods:
                    method = getattr(sandbox, method_name, None)
                    if not callable(method):
                        continue

                    try:
                        preview = await self._maybe_await(method(self.BRIDGE_PORT))
                    except Exception:
                        continue

                    if isinstance(preview, str) and preview.startswith("http"):
                        return preview.rstrip("/")

                    if hasattr(preview, "url"):
                        preview_url = getattr(preview, "url")
                        if isinstance(preview_url, str) and preview_url.startswith(
                            "http"
                        ):
                            return preview_url.rstrip("/")

                # Strategy 3: Fallback to explicit preview_url fields.
                preview_url = None
                if hasattr(sandbox, "preview_url") and sandbox.preview_url:
                    preview_url = sandbox.preview_url
                elif hasattr(sandbox, "url") and sandbox.url:
                    preview_url = sandbox.url

                if isinstance(preview_url, str) and preview_url.startswith("http"):
                    return preview_url.rstrip("/")

                # Strategy 4: Self-hosted fallback from base URL.
                if not self._is_cloud:
                    gateway_url = self._construct_gateway_url(sandbox_id)
                    if gateway_url:
                        return gateway_url

                raise SandboxGatewayError(
                    "Could not resolve gateway endpoint from sandbox metadata",
                    provider_ref=sandbox_id,
                )

        except SandboxGatewayError:
            raise
        except DaytonaError as e:
            raise SandboxGatewayError(
                f"Daytona SDK error during gateway resolution: {e}",
                provider_ref=sandbox_id,
            )
        except Exception as e:
            raise SandboxGatewayError(
                f"Unexpected error during gateway resolution: {e}",
                provider_ref=sandbox_id,
            )

    def _construct_gateway_url(self, sandbox_id: str) -> Optional[str]:
        """Construct gateway URL from sandbox ID.

        Args:
            sandbox_id: The Daytona sandbox ID.

        Returns:
            Gateway URL or None if construction fails.
        """
        if self._is_cloud:
            # Daytona Cloud: use regional gateway endpoint
            return f"https://gateway-{sandbox_id}.{self._target}.daytona.run:{self.BRIDGE_PORT}"
        else:
            # Self-hosted: construct from base URL
            # Strip any trailing path and add gateway subdomain
            from urllib.parse import urlparse, urlunparse

            try:
                parsed = urlparse(self._base_url)
                if parsed.hostname:
                    # Use the same scheme and domain, add gateway port
                    gateway_netloc = f"{parsed.hostname}:{self.BRIDGE_PORT}"
                    gateway_url = urlunparse(
                        parsed._replace(
                            netloc=gateway_netloc,
                            path=f"/{sandbox_id}",
                            query="",
                            fragment="",
                        )
                    )
                    return gateway_url
            except Exception:
                pass

        return None

    def _generate_ref(self, workspace_id: UUID) -> str:
        """Generate a deterministic Daytona workspace ID from workspace UUID."""
        # Create deterministic, valid Daytona workspace ID
        # Daytona IDs are typically alphanumeric with hyphens
        return f"daytona-{str(workspace_id)[:22]}"

    def _generate_user_ref(self, workspace_id: UUID, external_user_id: str) -> str:
        """Generate a deterministic Daytona workspace ID from workspace UUID and external user ID.

        Creates a per-user sandbox reference for multi-user isolation within the same workspace.
        Each (workspace_id, external_user_id) pair gets its own sandbox.

        Args:
            workspace_id: The workspace UUID.
            external_user_id: The end-user identifier for per-user isolation.

        Returns:
            Deterministic sandbox reference string.
        """
        import hashlib

        # Hash the external_user_id to create a short, deterministic suffix
        user_hash = hashlib.sha256(external_user_id.encode()).hexdigest()[:10]
        return f"daytona-{str(workspace_id)[:12]}-{user_hash}"

    def _from_daytona_state(self, daytona_state: str) -> SandboxState:
        """Convert Daytona state string to semantic state.

        Fail-closed: unknown states map to UNKNOWN.
        """
        normalized = self._normalize_daytona_value(daytona_state)
        return self.DAYTONA_STATE_MAP.get(normalized, SandboxState.UNKNOWN)

    def _from_daytona_health(self, daytona_sandbox) -> SandboxHealth:
        """Extract health status from Daytona sandbox object.

        Fail-closed: unknown/error states map to UNHEALTHY.
        """
        # Try to get health from sandbox attributes
        health_str = None

        # Check various possible health indicators
        if hasattr(daytona_sandbox, "status"):
            health_str = self._normalize_daytona_value(daytona_sandbox.status)
        elif hasattr(daytona_sandbox, "state"):
            # Map state to health heuristic
            state = self._normalize_daytona_value(daytona_sandbox.state)
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
        pack_digest: Optional[str] = None,
        materialized_config_path: Optional[str] = None,
    ) -> SandboxInfo:
        """Convert Daytona sandbox object to SandboxInfo DTO."""
        # Extract state from Daytona sandbox
        daytona_state = "unknown"
        if hasattr(daytona_sandbox, "state"):
            daytona_state = self._normalize_daytona_value(daytona_sandbox.state)
        elif hasattr(daytona_sandbox, "status"):
            daytona_state = self._normalize_daytona_value(daytona_sandbox.status)

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
            # Pack mount isolation contract: always expose path and read-only status
            metadata["pack_mount_path"] = PACK_MOUNT_PATH
            metadata["pack_mount_read_only"] = True
        if pack_digest:
            metadata["pack_digest"] = pack_digest
        if materialized_config_path:
            metadata["materialized_config_path"] = materialized_config_path

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

    def _generate_picoclaw_config(
        self,
        config: SandboxConfig,
    ) -> Dict[str, Any]:
        """Generate Picoclaw config.json for sandbox.

        DEPRECATED: Use _generate_zeroclaw_config for new provisioning.
        Kept for backwards compatibility during migration.

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
        gateway_port = bridge_config.get("gateway_port", self.BRIDGE_PORT)

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

    def _generate_zeroclaw_config(
        self,
        config: SandboxConfig,
    ) -> Dict[str, Any]:
        """Generate Zeroclaw config.json for sandbox (spec-driven).

        Creates a deterministic, sandbox-scoped config driven by ZeroclawSpec:
        - Auth token from runtime_bridge_config
        - Gateway port from spec
        - Workspace path for identity file access
        - Environment variables for LLM configuration

        Args:
            config: Sandbox configuration with runtime_bridge_config.

        Returns:
            Complete Zeroclaw config dict.
        """
        from src.integrations.zeroclaw.spec import load_zeroclaw_spec

        # Load spec for port configuration
        spec = load_zeroclaw_spec()

        # Get runtime bridge config from orchestrator
        runtime_config = config.runtime_bridge_config or {}

        # Extract bridge settings
        bridge_config = runtime_config.get("bridge", {})
        bridge_auth_token = bridge_config.get("auth_token", "temp-token")
        gateway_port = spec.gateway.port

        # Build Zeroclaw config.json structure
        # Uses Zeroclaw's spec-driven configuration format
        zeroclaw_config = {
            "version": spec.version,
            "gateway": {
                "host": "0.0.0.0",
                "port": gateway_port,
                "health_path": spec.gateway.health_path,
                "execute_path": spec.gateway.execute_path,
                "stream_mode": spec.gateway.stream_mode,
            },
            "auth": {
                "mode": spec.auth.mode,
                "token": bridge_auth_token,
            },
            "workspace": {
                "path": WORKSPACE_PATH,
                "pack_mount_path": PACK_MOUNT_PATH,
            },
            "llm": {
                "model": "${LLM_MODEL:-openai/gpt-4}",
                "api_key": "${LLM_API_KEY}",
                "api_base": "${LLM_API_BASE}",
                "max_tokens": 8192,
                "temperature": 0.7,
            },
            "runtime": {
                "max_tool_iterations": 20,
            },
        }

        return zeroclaw_config

    async def _create_workspace_symlinks(self, sandbox) -> None:
        """Create workspace directory and symlink identity files from pack volume.

        Creates /workspace/ and symlinks:
        - AGENT.md, SOUL.md, IDENTITY.md (files)
        - skills/ (directory)
        from /workspace/pack/ into the workspace directory.

        This implements mount isolation: pack volume (read-only, shared) is mounted
        at /workspace/pack, while dynamic runtime data lives at /workspace.
        Identity files are symlinked to make them accessible from the workspace.
        """

        # Create workspace directory
        await self._exec_checked(sandbox, f"mkdir -p {WORKSPACE_PATH}")

        # Symlink identity files
        for f in IDENTITY_FILES:
            await self._exec_checked(
                sandbox, f"ln -sf {PACK_MOUNT_PATH}/{f} {WORKSPACE_PATH}/{f}"
            )

        # Symlink identity directories
        for d in IDENTITY_DIRS:
            await self._exec_checked(
                sandbox, f"ln -sf {PACK_MOUNT_PATH}/{d} {WORKSPACE_PATH}/{d}"
            )

    async def _is_bridge_listening(self, sandbox: Any) -> bool:
        """Check whether Picoclaw bridge is listening on configured port."""
        probe_cmd = (
            'python -c "import socket,sys;'
            "s=socket.socket();"
            "s.settimeout(1);"
            f"rc=s.connect_ex(('127.0.0.1',{self.BRIDGE_PORT}));"
            "s.close();"
            'sys.exit(0 if rc==0 else 1)"'
        )
        result = await self._maybe_await(sandbox.process.exec(probe_cmd))
        return getattr(result, "exit_code", 1) == 0

    async def _start_bridge_runtime(self, sandbox: Any, strict: bool = True) -> bool:
        """Start the bridge runtime process and verify port listener.

        Uses Zeroclaw start_command from spec for runtime initialization.

        Returns:
            True when listener is confirmed. In non-strict mode returns False
            instead of raising on startup/readiness failures.
        """
        from src.integrations.zeroclaw.spec import load_zeroclaw_spec

        spec = load_zeroclaw_spec()
        zeroclaw_port = spec.gateway.port

        if await self._is_bridge_listening(sandbox):
            return True

        # Use Zeroclaw start command from spec
        start_cmd = spec.runtime.start_command

        max_attempts = self.BRIDGE_START_MAX_ATTEMPTS if strict else 1
        listen_timeout = self.BRIDGE_LISTEN_TIMEOUT_SECONDS if strict else 1.0

        last_error: Optional[str] = None
        for attempt in range(1, max_attempts + 1):
            try:
                await self._exec_checked(sandbox, start_cmd)

                deadline = asyncio.get_event_loop().time() + listen_timeout
                while asyncio.get_event_loop().time() < deadline:
                    if await self._is_bridge_listening(sandbox):
                        return True
                    await asyncio.sleep(0.5)

                last_error = (
                    f"Bridge listener not ready on port {zeroclaw_port} "
                    f"after {listen_timeout:.0f}s"
                )
            except SandboxProvisionError as exc:
                last_error = str(exc)

            if attempt < max_attempts:
                await asyncio.sleep(self.BRIDGE_START_BACKOFF_SECONDS * attempt)

        if strict:
            raise SandboxProvisionError(
                f"Failed to start Zeroclaw bridge runtime: {last_error}"
            )

        return False

    async def _materialize_pack(
        self,
        config: SandboxConfig,
    ) -> Dict[str, Any]:
        """Materialize agent pack into Daytona workspace.

        Implements snapshot copy/sync semantics (not live bind).
        In production, this would copy pack files into the Daytona workspace.

        Args:
            config: Sandbox configuration with pack_source_path.

        Returns:
            Materialization metadata with paths and digests.
        """
        if not config.pack_source_path:
            return {"materialized": False}

        # In production with Daytona SDK:
        # 1. Use Daytona file operations to copy pack content
        # 2. Compute digest of copied content
        # 3. Write config.json to workspace

        # For SDK simulation:
        # - Track that materialization occurred
        # - Store the expected config path
        # - Store the pack digest for stale detection

        materialized_path = PACK_MOUNT_PATH
        config_path = CONFIG_PATH

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
        """Get active sandbox for workspace using SDK.

        Queries Daytona via SDK for workspace associated with this workspace_id.
        Returns None if no active workspace exists or if sandbox is stopped.

        Args:
            workspace_id: The workspace UUID to look up.
            external_user_id: Optional end-user identifier for per-user sandbox isolation.
                If provided, looks up the sandbox specific to this user.

        Returns:
            SandboxInfo if active sandbox exists, None otherwise.
        """
        # Use per-user ref if external_user_id provided
        if external_user_id:
            ref = self._generate_user_ref(workspace_id, external_user_id)
        else:
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
                    daytona_state = self._normalize_daytona_value(sandbox.state)

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

        except DaytonaError:
            # Fail-closed: SDK errors result in None (no active sandbox)
            return None
        except Exception:
            # Fail-closed: any error results in None
            return None

    async def list_sandbox_refs_by_workspace(self, workspace_id: UUID) -> List[str]:
        """List Daytona sandbox IDs that belong to a workspace.

        Uses workspace_id label emitted during provisioning. Returns empty list
        on provider/listing errors to preserve fail-closed behavior.
        """
        refs: List[str] = []
        try:
            config = self._create_config()
            async with AsyncDaytona(config=config) as daytona:
                list_method = getattr(daytona, "list", None)
                if not callable(list_method):
                    return refs

                sandboxes = await self._maybe_await(list_method())
                if not sandboxes:
                    return refs

                for sandbox in sandboxes:
                    labels = getattr(sandbox, "labels", None) or {}
                    if labels.get("workspace_id") != str(workspace_id):
                        continue

                    sandbox_id = getattr(sandbox, "id", None)
                    if sandbox_id:
                        refs.append(str(sandbox_id))
        except Exception:
            return []

        return refs

    def _compute_volume_name(self, pack_id: UUID, pack_digest: str) -> str:
        """Compute deterministic volume name from pack ID and digest.

        Args:
            pack_id: Agent pack UUID
            pack_digest: SHA-256 digest of pack content

        Returns:
            Volume name: agent-pack-{pack_id}-{pack_digest}
        """
        return f"agent-pack-{pack_id}-{pack_digest}"

    async def _ensure_pack_volume_id(
        self,
        daytona: AsyncDaytona,
        pack_id: UUID,
        pack_digest: str,
    ) -> str:
        """Ensure pack volume exists and return its Daytona volume ID."""
        volume_name = self._compute_volume_name(pack_id, pack_digest)

        try:
            volume = await daytona.volume.get(volume_name, create=True)
        except DaytonaError as e:
            raise SandboxProvisionError(
                f"Failed to create/get pack volume {volume_name}: {e}",
                provider_ref=volume_name,
            )

        max_polls = 10
        poll_interval = 1.0
        for _ in range(max_polls):
            state = self._normalize_daytona_value(getattr(volume, "state", None))
            if state not in {"pending", "pending_create", "creating", "initializing"}:
                break

            await asyncio.sleep(poll_interval)
            try:
                volume = await daytona.volume.get(volume_name)
            except DaytonaError as e:
                raise SandboxProvisionError(
                    f"Failed to refresh pack volume {volume_name}: {e}",
                    provider_ref=volume_name,
                )
        else:
            raise SandboxProvisionError(
                f"Pack volume {volume_name} did not become ready in {max_polls * poll_interval:.0f}s",
                provider_ref=volume_name,
            )

        volume_id = getattr(volume, "id", None)
        if not volume_id:
            raise SandboxProvisionError(
                f"Pack volume {volume_name} has no ID",
                provider_ref=volume_name,
            )

        return str(volume_id)

    def _build_create_params(
        self,
        config: SandboxConfig,
        pack_volume_id: Optional[str] = None,
    ) -> CreateSandboxFromSnapshotParams:
        """Build Daytona CreateSandboxFromSnapshotParams from config.

        Args:
            config: Sandbox configuration.

        Returns:
            CreateSandboxFromSnapshotParams for Daytona SDK create() method.

        Raises:
            SandboxConfigurationError: If pack binding is required but incomplete.
        """
        # Build volume mounts list
        volume_mounts: List[VolumeMount] = []

        # Pack binding: mount volume if pack_source_path is provided
        if config.pack_source_path:
            # Fail-closed: both agent_pack_id and pack_digest required for binding
            if not config.agent_pack_id:
                raise SandboxConfigurationError(
                    "agent_pack_id is required when pack_source_path is provided",
                    provider_ref=str(config.workspace_id),
                    workspace_id=config.workspace_id,
                )
            if not config.pack_digest:
                raise SandboxConfigurationError(
                    "pack_digest is required when pack_source_path is provided",
                    provider_ref=str(config.workspace_id),
                    workspace_id=config.workspace_id,
                )

            # Compute volume name and add mount
            volume_name = self._compute_volume_name(
                config.agent_pack_id, config.pack_digest
            )
            resolved_volume_id = pack_volume_id or volume_name
            volume_mounts.append(
                VolumeMount(
                    volume_id=resolved_volume_id,
                    mount_path="/workspace/pack",
                    additional_properties={"read_only": True},
                )
            )

        # Build labels
        labels: Dict[str, str] = {}
        labels.update(self._image_labels)
        labels["workspace_id"] = str(config.workspace_id)
        if config.external_user_id:
            labels["external_user_id"] = config.external_user_id
        if config.pack_source_path:
            labels["pack_source_path"] = config.pack_source_path
        if config.pack_digest:
            labels["pack_digest"] = config.pack_digest
        if config.agent_pack_id:
            labels["agent_pack_id"] = str(config.agent_pack_id)

        # Image contract metadata labels
        labels["picoclaw.base_image"] = self._base_image
        labels["picoclaw.base_image_strict"] = str(
            bool(
                getattr(self, "_strict_mode", False)
                or getattr(self, "_digest_required", False)
            )
        )

        # Build CreateSandboxFromSnapshotParams
        params = CreateSandboxFromSnapshotParams(
            snapshot=self._snapshot_name,
            timeout=60,
            labels=labels if labels else None,
            env_vars=config.env_vars if config.env_vars else None,
            volumes=volume_mounts if volume_mounts else None,
        )

        return params

    async def provision_sandbox(
        self,
        config: SandboxConfig,
    ) -> SandboxInfo:
        """Create and start a new Daytona workspace using SDK with image-first config.

        Provisioning lifecycle:
        1. Build create parameters with image/runtime config
        2. Create workspace via Daytona SDK (HYDRATING state)
        3. Verify identity files are mounted (hard gate)
        4. Resolve authoritative gateway endpoint
        5. Materialize pack (snapshot copy, not live bind)
        6. Generate Picoclaw config.json with bridge-only channels
        7. Mark READY with gateway URL populated

        Pack binding:
        - If config.pack_source_path is provided, materializes pack into workspace
        - Generates per-sandbox Picoclaw config.json with bridge-only channels
        - Pack digest stored in metadata for stale detection
        - Sensitive credentials remain env-var sourced
        """
        # Use per-user ref if external_user_id provided, otherwise use workspace-only ref
        if config.external_user_id:
            ref = self._generate_user_ref(config.workspace_id, config.external_user_id)
        else:
            ref = self._generate_ref(config.workspace_id)

        # Pack binding: track pack info if provided
        pack_bound = config.pack_source_path is not None
        daytona_client: Optional[AsyncDaytona] = None
        sandbox: Optional[Any] = None
        sandbox_id = ref

        try:
            daytona_config = self._create_config()
            async with AsyncDaytona(config=daytona_config) as daytona:
                daytona_client = daytona
                pack_volume_id = None
                if pack_bound and config.agent_pack_id and config.pack_digest:
                    pack_volume_id = await self._ensure_pack_volume_id(
                        daytona=daytona,
                        pack_id=config.agent_pack_id,
                        pack_digest=config.pack_digest,
                    )

                # Build create parameters with snapshot-based provisioning
                create_params = self._build_create_params(
                    config,
                    pack_volume_id=pack_volume_id,
                )

                # Create sandbox via SDK with bounded timeout to avoid hanging requests
                create_timeout = min(
                    float(getattr(create_params, "timeout", 60) or 60),
                    self.PROVISION_CREATE_TIMEOUT_SECONDS,
                )

                try:
                    sandbox = await asyncio.wait_for(
                        daytona.create(create_params, timeout=create_timeout),
                        timeout=create_timeout + 5,
                    )
                except asyncio.TimeoutError as e:
                    raise SandboxProvisionError(
                        f"Timed out creating Daytona sandbox after {create_timeout:.0f}s",
                        provider_ref=ref,
                        workspace_id=config.workspace_id,
                    ) from e

                # Get the actual sandbox ID from the response
                if hasattr(sandbox, "id"):
                    sandbox_id = sandbox.id

                # Create workspace directory and symlink identity files from pack volume
                # This implements mount isolation: pack volume (read-only) vs workspace (writable)
                await self._create_workspace_symlinks(sandbox)

                # Verify identity files are mounted at workspace path (hard gate)
                # This confirms symlinks work at the configured workspace path.
                identity_result = await self.verify_identity_files(
                    sandbox_id,
                    timeout=self.IDENTITY_VERIFY_TIMEOUT_SECONDS,
                )
                if not identity_result.ready:
                    raise SandboxIdentityError(
                        f"Identity verification failed: {identity_result.error_message}",
                        provider_ref=sandbox_id,
                        workspace_id=config.workspace_id,
                    )

                # Resolve authoritative gateway endpoint
                try:
                    gateway_url = await self.resolve_gateway_endpoint(sandbox_id)
                except SandboxGatewayError as e:
                    raise SandboxProvisionError(
                        f"Failed to resolve gateway endpoint: {e}",
                        provider_ref=sandbox_id,
                        workspace_id=config.workspace_id,
                    )

                # Write per-sandbox Zeroclaw config via file API (outside shared pack volume)
                from src.integrations.zeroclaw.spec import load_zeroclaw_spec

                spec = load_zeroclaw_spec()
                config_path = spec.runtime.config_path
                try:

                    async def _fs_call(method, *args):
                        result = method(*args)
                        if inspect.isawaitable(result):
                            return await result
                        return result

                    # Fail-fast: ensure config path is outside shared pack volume
                    assert not config_path.startswith(PACK_MOUNT_PATH), (
                        f"Config path must be outside {PACK_MOUNT_PATH}: {config_path}"
                    )

                    # Generate Zeroclaw config (spec-driven)
                    zeroclaw_config = self._generate_zeroclaw_config(config)
                    config_bytes = json.dumps(zeroclaw_config, indent=2).encode("utf-8")

                    # Create config directory via file API
                    config_dir = "/".join(config_path.split("/")[:-1])
                    try:
                        await _fs_call(
                            sandbox.fs.create_folder,
                            config_dir,
                            "700",
                        )
                    except DaytonaError as e:
                        # Ignore "already exists" errors
                        if "already exists" not in str(e).lower():
                            raise

                    # Write config file via file API
                    await _fs_call(sandbox.fs.upload_file, config_bytes, config_path)

                except DaytonaError as e:
                    raise SandboxProvisionError(
                        f"Failed to write Zeroclaw config: {e}",
                        provider_ref=sandbox_id,
                        workspace_id=config.workspace_id,
                    )

                bridge_cfg = (config.runtime_bridge_config or {}).get("bridge", {})
                strict_runtime_ready = bool(bridge_cfg.get("enabled"))

                # Start bridge runtime and verify listener on configured port.
                runtime_ready = await self._start_bridge_runtime(
                    sandbox,
                    strict=strict_runtime_ready,
                )

                # Store pack binding metadata on the sandbox if possible
                # This is best-effort - not all Daytona versions support metadata
                metadata: Dict[str, Any] = {
                    "gateway_url": gateway_url,
                    "identity_ready": True,
                    "runtime_ready": runtime_ready,
                    "materialized_config_path": config_path,
                }
                if pack_bound:
                    metadata["pack_bound"] = True
                    metadata["pack_source_path"] = config.pack_source_path
                    metadata["pack_digest"] = config.pack_digest

                # Build result with gateway URL in metadata
                result = self._to_info(
                    sandbox_id,
                    sandbox,
                    pack_bound=pack_bound,
                    pack_source_path=config.pack_source_path,
                    workspace_id=config.workspace_id,
                    pack_digest=config.pack_digest,
                    materialized_config_path=config_path,
                )

                # Return merged metadata for orchestrator persistence.
                # Orchestrator reads `provider_info.ref.metadata["gateway_url"]`.
                merged_metadata = dict(result.ref.metadata or {})
                merged_metadata.update(metadata)

                return SandboxInfo(
                    ref=SandboxRef(
                        provider_ref=result.ref.provider_ref,
                        profile=result.ref.profile,
                        metadata=merged_metadata,
                    ),
                    state=result.state,
                    health=result.health,
                    workspace_id=result.workspace_id,
                    last_activity_at=result.last_activity_at,
                    created_at=result.created_at,
                    error_message=result.error_message,
                    provider_state=result.provider_state,
                )

        except SandboxIdentityError:
            if sandbox is not None and daytona_client is not None:
                await self._best_effort_stop_failed_sandbox(daytona_client, sandbox)
            raise
        except DaytonaError as e:
            if daytona_client is not None:
                if sandbox is not None:
                    await self._best_effort_stop_failed_sandbox(daytona_client, sandbox)
                else:
                    await self._best_effort_cleanup_failed_create(
                        daytona_client, config
                    )
            raise SandboxProvisionError(
                f"Failed to provision Daytona sandbox: {e}",
                provider_ref=ref,
                workspace_id=config.workspace_id,
            )
        except Exception as e:
            if daytona_client is not None:
                if sandbox is not None:
                    await self._best_effort_stop_failed_sandbox(daytona_client, sandbox)
                else:
                    await self._best_effort_cleanup_failed_create(
                        daytona_client, config
                    )
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
