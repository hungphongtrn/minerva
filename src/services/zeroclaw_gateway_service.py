"""Zeroclaw gateway service for synchronous HTTP execution against in-sandbox Zeroclaw gateway.

This service provides:
- Health-first execution: polls /health before any execute request
- Bearer token authentication on both health and execute calls
- Typed errors for health failure, auth failure, timeout, upstream non-2xx responses
- Deterministic retry and timeout behavior
- Fail-closed semantics: never attempts execution when health/auth checks fail

The service is driven by ZeroclawSpec from the integration spec file.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import httpx
from urllib.parse import urljoin

from src.config.settings import settings
from src.integrations.zeroclaw.spec import load_zeroclaw_spec, ZeroclawSpec


class GatewayErrorType(str, Enum):
    """Typed error categories for gateway failures."""

    HEALTH_CHECK_FAILED = "health_check_failed"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    UPSTREAM_ERROR = "upstream_error"
    MALFORMED_RESPONSE = "malformed_response"


@dataclass
class GatewayError:
    """Structured error from gateway operations."""

    error_type: GatewayErrorType
    message: str
    status_code: Optional[int] = None
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "error_type": self.error_type.value,
            "message": self.message,
        }
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.remediation:
            result["remediation"] = self.remediation
        return result


@dataclass
class GatewayResult:
    """Result of a gateway execution."""

    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[GatewayError] = None

    def to_dict(self) -> Dict[str, Any]:
        if self.success:
            return {"success": True, "output": self.output}
        return {"success": False, "error": self.error.to_dict() if self.error else None}


@dataclass
class GatewayTokenBundle:
    """Token bundle for sandbox-scoped gateway authentication.

    Per-sandbox authentication with grace-period rotation support.
    Contains the current token and optionally a previous token
    that remains valid during cutover periods.
    """

    current: str
    """Current active gateway authentication token."""

    previous: Optional[str] = None
    """Previous token valid during grace period rotation."""

    previous_expires_at: Optional[datetime] = None
    """Expiry timestamp for previous token grace period."""

    def is_grace_token_valid(self) -> bool:
        """Check if the previous/grace token is still valid.

        Returns:
            True if previous token exists and hasn't expired.
        """
        if not self.previous or not self.previous_expires_at:
            return False
        return datetime.utcnow() < self.previous_expires_at

    def get_effective_token(self, attempt: int = 0) -> str:
        """Get the token to use for authentication.

        On first attempt, uses current token. On retry and if
        grace token is still valid, may attempt with previous token.

        Args:
            attempt: Retry attempt number (0 = first attempt)

        Returns:
            Token string for Authorization header.
        """
        if attempt == 0:
            return self.current
        # On retry, if grace token is valid, try it
        if self.is_grace_token_valid():
            return self.previous
        return self.current


@dataclass
class HealthStatus:
    """Health check response from Zeroclaw gateway."""

    healthy: bool
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ZeroclawGatewayService:
    """Gateway service for synchronous HTTP execution against in-sandbox Zeroclaw gateway.

    This service implements:
    - Health-first execution: always polls /health before execute
    - Bearer token authentication (when spec requires bearer)
    - Fail-closed: execution is blocked if health/auth checks fail
    - Typed errors with remediation guidance
    - Deterministic retry and timeout behavior
    - Spec-driven: paths and port loaded from ZeroclawSpec
    """

    # Default configuration values
    DEFAULT_HEALTH_TIMEOUT = 10  # seconds
    DEFAULT_HEALTH_RETRIES = 3
    DEFAULT_HEALTH_BACKOFF = 1.0  # seconds
    DEFAULT_EXECUTE_TIMEOUT = 300  # 5 minutes
    DEFAULT_EXECUTE_RETRIES = 0  # No retries for execute by default (synchronous phase)

    def __init__(
        self,
        spec: Optional[ZeroclawSpec] = None,
        health_timeout: Optional[int] = None,
        health_retries: Optional[int] = None,
        health_backoff: Optional[float] = None,
        execute_timeout: Optional[int] = None,
        execute_retries: Optional[int] = None,
    ):
        """Initialize the gateway service.

        Args:
            spec: ZeroclawSpec instance. If None, loads from default path.
            health_timeout: Timeout for health check requests in seconds
            health_retries: Number of retries for health check failures
            health_backoff: Backoff delay between health check retries
            execute_timeout: Timeout for execute requests in seconds
            execute_retries: Number of retries for execute failures
        """
        # Load spec if not provided
        self._spec = spec or load_zeroclaw_spec()

        # Load from settings with fallbacks to defaults
        zeroclaw_config = getattr(settings, "ZEROCLAW_GATEWAY", None) or {}

        self.health_timeout = (
            health_timeout or zeroclaw_config.get("HEALTH_TIMEOUT") or self.DEFAULT_HEALTH_TIMEOUT
        )
        self.health_retries = (
            health_retries or zeroclaw_config.get("HEALTH_RETRIES") or self.DEFAULT_HEALTH_RETRIES
        )
        self.health_backoff = (
            health_backoff or zeroclaw_config.get("HEALTH_BACKOFF") or self.DEFAULT_HEALTH_BACKOFF
        )
        self.execute_timeout = (
            execute_timeout
            or zeroclaw_config.get("EXECUTE_TIMEOUT")
            or self.DEFAULT_EXECUTE_TIMEOUT
        )
        self.execute_retries = (
            execute_retries
            or zeroclaw_config.get("EXECUTE_RETRIES")
            or self.DEFAULT_EXECUTE_RETRIES
        )

    @property
    def spec(self) -> ZeroclawSpec:
        """Get the Zeroclaw spec used by this service."""
        return self._spec

    def _requires_auth(self) -> bool:
        """Check if authentication is required per spec."""
        return self._spec.auth.mode == "bearer"

    def _get_health_url(self, sandbox_url: str) -> str:
        """Build health check URL from spec and sandbox URL."""
        base = sandbox_url.rstrip("/")
        path = self._spec.gateway.health_path
        return urljoin(base + "/", path.lstrip("/"))

    def _get_execute_url(self, sandbox_url: str) -> str:
        """Build execute URL from spec and sandbox URL."""
        base = sandbox_url.rstrip("/")
        path = self._spec.gateway.execute_path
        return urljoin(base + "/", path.lstrip("/"))

    def _get_execute_candidate_urls(self, sandbox_url: str) -> list[str]:
        """Build candidate execute URLs with bidirectional compatibility fallback.

        Primary route always comes from spec.gateway.execute_path.
        If the primary is `/webhook`, include `/execute` as a compatibility
        fallback for legacy runtimes that expose only the execute route.
        If the primary is `/execute`, include `/webhook` as a compatibility
        fallback for runtimes that expose webhook ingress instead.
        """
        primary = self._get_execute_url(sandbox_url)

        # Determine fallback based on primary path
        if primary.endswith("/webhook"):
            fallback = urljoin(sandbox_url.rstrip("/") + "/", "execute")
        elif primary.endswith("/execute"):
            fallback = urljoin(sandbox_url.rstrip("/") + "/", "webhook")
        else:
            # Unknown path - no fallback, try primary only
            return [primary]

        if primary == fallback:
            return [primary]

        return [primary, fallback]

    def _get_auth_headers(
        self, token_bundle: GatewayTokenBundle, attempt: int = 0
    ) -> Dict[str, str]:
        """Get authentication headers for requests using sandbox-scoped token.

        Args:
            token_bundle: Sandbox-specific token bundle with current and grace tokens
            attempt: Retry attempt number for grace-token fallback on rotation

        Returns:
            Dictionary of headers including Authorization
        """
        token = token_bundle.get_effective_token(attempt)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _request_with_auth_fallback(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        token_bundle: Optional[GatewayTokenBundle],
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with one-time auth fallback on 401/403.

        On first attempt, uses current token. If 401/403 received and grace
        token is valid, retries exactly once with the previous token.

        Args:
            client: httpx AsyncClient instance
            method: HTTP method ("get", "post", etc.)
            url: Request URL
            token_bundle: Token bundle with current and optional grace token
            **kwargs: Additional arguments passed to client.request()

        Returns:
            Final httpx.Response (from current or grace token attempt)
        """
        headers = kwargs.pop("headers", {})
        base_headers = {"Content-Type": "application/json"}
        base_headers.update(headers)

        # First attempt with current token
        if token_bundle and self._requires_auth():
            auth_headers = self._get_auth_headers(token_bundle, attempt=0)
            base_headers.update(auth_headers)

        response = await client.request(method, url, headers=base_headers, **kwargs)

        # On 401/403, retry once with grace token if valid
        if response.status_code in (401, 403):
            if token_bundle and self._requires_auth() and token_bundle.is_grace_token_valid():
                # Retry with previous/grace token
                grace_headers = {"Content-Type": "application/json"}
                grace_headers.update(headers)
                grace_auth = self._get_auth_headers(token_bundle, attempt=1)
                grace_headers.update(grace_auth)
                response = await client.request(method, url, headers=grace_headers, **kwargs)

        return response

    async def check_health(
        self, sandbox_url: str, token_bundle: Optional[GatewayTokenBundle] = None
    ) -> HealthStatus:
        """Check health of Zeroclaw gateway in sandbox.

        Args:
            sandbox_url: Base URL of the sandbox gateway
            token_bundle: Sandbox-scoped authentication tokens. If None, health
                check proceeds without authentication (may fail with 401 if spec
                requires bearer auth).

        Returns:
            HealthStatus with healthy flag and details
        """
        health_url = self._get_health_url(sandbox_url)

        async with httpx.AsyncClient(timeout=self.health_timeout) as client:
            try:
                response = await self._request_with_auth_fallback(
                    client, "GET", health_url, token_bundle
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        return HealthStatus(
                            healthy=True,
                            status=data.get("status", "ok"),
                            details=data,
                        )
                    except Exception:
                        # Response wasn't JSON, but 200 means healthy
                        return HealthStatus(healthy=True, status="ok")
                elif response.status_code == 401 or response.status_code == 403:
                    return HealthStatus(
                        healthy=False,
                        status="unauthorized",
                        details={"status_code": response.status_code},
                    )
                else:
                    return HealthStatus(
                        healthy=False,
                        status="unhealthy",
                        details={"status_code": response.status_code},
                    )

            except httpx.TimeoutException:
                return HealthStatus(healthy=False, status="timeout")
            except httpx.RequestError as e:
                return HealthStatus(healthy=False, status="error", details={"error": str(e)})

    async def poll_health(
        self,
        sandbox_url: str,
        token_bundle: Optional[GatewayTokenBundle] = None,
    ) -> HealthStatus:
        """Poll health with retries and exponential backoff.

        This implements deterministic retry behavior:
        - Always polls /health before execution
        - Retries on transient failures with bounded backoff
        - Fails-closed: returns unhealthy status after exhausting retries

        Args:
            sandbox_url: Base URL of the sandbox gateway
            token_bundle: Sandbox-scoped authentication tokens

        Returns:
            HealthStatus with final healthy/unhealthy state
        """
        last_status = None

        for attempt in range(self.health_retries + 1):
            status = await self.check_health(sandbox_url, token_bundle)
            last_status = status

            if status.healthy:
                return status

            # Wait before retry with exponential backoff
            if attempt < self.health_retries:
                await asyncio.sleep(self.health_backoff * (2**attempt))

        # Return the last status after exhausting retries
        return last_status or HealthStatus(healthy=False, status="unknown")

    def _transform_to_zeroclaw_request(
        self,
        message: str,
        session_key: str,
        workspace_id: Optional[str] = None,
        agent_pack_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sender_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transform Minerva envelope to Zeroclaw execute request format.

        Uses the spec examples as a base template.

        Args:
            message: The message content from Minerva request
            session_key: Session key for continuity
            workspace_id: Workspace ID for scoping
            agent_pack_id: Agent pack ID if bound
            run_id: Run ID for tracing
            metadata: Additional metadata
            sender_id: External user identifier for conversation scoping
            session_id: Session ID for thread continuity

        Returns:
            Zeroclaw-format request dictionary
        """
        # Start from spec example and override with provided values
        request = {
            "message": message,
            "context": {
                "session_id": session_id or session_key,
                "sender_id": sender_id or "minerva",
                "workspace_id": workspace_id,
                "agent_pack_id": agent_pack_id,
                "run_id": run_id,
                **(metadata or {}),
            },
        }

        return request

    async def execute(
        self,
        sandbox_url: str,
        message: str,
        session_key: str,
        token_bundle: GatewayTokenBundle,
        workspace_id: Optional[str] = None,
        agent_pack_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sender_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewayResult:
        """Execute request via gateway with health-first fail-closed flow.

        This method:
        1. Polls /health before any execution (fail-closed)
        2. Attaches bearer token to execution request if spec requires auth
        3. Returns typed errors for all failure modes
        4. Respects timeout and retry configuration
        5. Handles token rotation with grace-period fallback

        Args:
            sandbox_url: Base URL of the sandbox gateway
            message: The message to send to Zeroclaw
            session_key: Session key for continuity
            token_bundle: Sandbox-scoped authentication tokens with rotation support
            workspace_id: Workspace ID for scoping
            agent_pack_id: Agent pack ID if bound
            run_id: Run ID for tracing
            metadata: Additional metadata
            sender_id: External user identifier for conversation scoping
            session_id: Session ID for thread continuity

        Returns:
            GatewayResult with success/output or error details
        """
        # Fail-closed: require token_bundle if auth is required
        if self._requires_auth() and (not token_bundle or not token_bundle.current):
            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.AUTH_FAILED,
                    message="Gateway authentication failed: token bundle required",
                    remediation="Token bundle must be resolved from sandbox metadata with valid current token",
                ),
            )

        # Step 1: Health check (fail-closed)
        health = await self.poll_health(sandbox_url, token_bundle)

        if not health.healthy:
            error_type = GatewayErrorType.HEALTH_CHECK_FAILED
            if health.status == "unauthorized":
                error_type = GatewayErrorType.AUTH_FAILED

            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=error_type,
                    message=f"Health check failed: {health.status}",
                    remediation="Sandbox may be unhealthy or unreachable. Try again later or reprovision.",
                ),
            )

        # Step 2: Transform request to Zeroclaw format
        zeroclaw_request = self._transform_to_zeroclaw_request(
            message=message,
            session_key=session_key,
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            run_id=run_id,
            metadata=metadata,
            sender_id=sender_id,
            session_id=session_id,
        )

        # Step 3: Execute request with retries and auth fallback
        execute_urls = self._get_execute_candidate_urls(sandbox_url)
        last_error = None
        auth_fallback_attempted = False

        for attempt in range(self.execute_retries + 1):
            async with httpx.AsyncClient(timeout=self.execute_timeout) as client:
                try:
                    headers = {"Content-Type": "application/json"}
                    if token_bundle and self._requires_auth():
                        headers = self._get_auth_headers(token_bundle, attempt=0)

                    for url_idx, execute_url in enumerate(execute_urls):
                        response = await client.post(
                            execute_url,
                            headers=headers,
                            json=zeroclaw_request,
                        )

                        # Compatibility fallback: retry /webhook if primary route is missing
                        if response.status_code == 404 and url_idx == 0 and len(execute_urls) > 1:
                            continue

                        # Auth fallback: retry once with grace token on 401/403
                        if (
                            response.status_code in (401, 403)
                            and not auth_fallback_attempted
                            and token_bundle
                            and self._requires_auth()
                            and token_bundle.is_grace_token_valid()
                        ):
                            auth_fallback_attempted = True
                            # Retry with grace token (attempt=1 uses previous token)
                            grace_headers = {"Content-Type": "application/json"}
                            grace_headers.update(self._get_auth_headers(token_bundle, attempt=1))
                            response = await client.post(
                                execute_url,
                                headers=grace_headers,
                                json=zeroclaw_request,
                            )

                        if response.status_code == 200:
                            try:
                                data = response.json()
                                return GatewayResult(success=True, output=data)
                            except Exception as e:
                                return GatewayResult(
                                    success=False,
                                    error=GatewayError(
                                        error_type=GatewayErrorType.MALFORMED_RESPONSE,
                                        message="Failed to parse response",
                                        remediation="Contact support - response format may have changed.",
                                    ),
                                )
                        elif response.status_code == 401 or response.status_code == 403:
                            return GatewayResult(
                                success=False,
                                error=GatewayError(
                                    error_type=GatewayErrorType.AUTH_FAILED,
                                    message="Authentication failed",
                                    status_code=response.status_code,
                                    remediation="Check gateway token configuration.",
                                ),
                            )
                        else:
                            # Non-2xx response from upstream
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("error", "Unknown error")
                            except Exception:
                                error_msg = f"HTTP {response.status_code}"

                            last_error = GatewayError(
                                error_type=GatewayErrorType.UPSTREAM_ERROR,
                                message=error_msg,
                                status_code=response.status_code,
                                remediation="Check Zeroclaw gateway logs for details.",
                            )

                            # Don't retry on 4xx errors (except handled above)
                            if 400 <= response.status_code < 500:
                                return GatewayResult(success=False, error=last_error)

                            # Retry on 5xx using outer attempt loop
                            break

                except httpx.TimeoutException:
                    last_error = GatewayError(
                        error_type=GatewayErrorType.TIMEOUT,
                        message=f"Request timed out after {self.execute_timeout}s",
                        remediation="Increase ZEROCLAW_GATEWAY.EXECUTE_TIMEOUT or check sandbox performance.",
                    )
                except httpx.RequestError as e:
                    last_error = GatewayError(
                        error_type=GatewayErrorType.TRANSPORT_ERROR,
                        message=f"Transport error: {str(e)}",
                        remediation="Check network connectivity to sandbox.",
                    )

                # Wait before retry with backoff
                if attempt < self.execute_retries:
                    await asyncio.sleep(self.health_backoff * (2**attempt))

        # Return last error if all retries exhausted
        return GatewayResult(success=False, error=last_error)


# Module-level convenience function
async def execute_via_gateway(
    sandbox_url: str,
    message: str,
    session_key: str,
    token_bundle: Optional[GatewayTokenBundle] = None,
    workspace_id: Optional[str] = None,
    agent_pack_id: Optional[str] = None,
    run_id: Optional[str] = None,
    sender_id: Optional[str] = None,
    session_id: Optional[str] = None,
    spec: Optional[ZeroclawSpec] = None,
) -> GatewayResult:
    """Execute a message via the Zeroclaw gateway.

    Convenience function that creates a gateway service and executes the request.
    Note: If spec requires bearer auth, this requires a token_bundle.
    Without token_bundle when auth is required, the call will fail-closed with AUTH_FAILED.

    Args:
        sandbox_url: Base URL of the sandbox gateway
        message: The message to send
        session_key: Session key for continuity
        token_bundle: Sandbox-scoped authentication tokens (required if spec needs auth)
        workspace_id: Workspace ID for scoping
        agent_pack_id: Agent pack ID if bound
        run_id: Run ID for tracing
        sender_id: External user identifier for conversation scoping
        session_id: Session ID for thread continuity
        spec: Optional ZeroclawSpec instance (loads default if not provided)

    Returns:
        GatewayResult with execution outcome
    """
    service = ZeroclawGatewayService(spec=spec)

    # Fail-closed: require token_bundle if auth is required
    if service._requires_auth() and not token_bundle:
        return GatewayResult(
            success=False,
            error=GatewayError(
                error_type=GatewayErrorType.AUTH_FAILED,
                message="Gateway authentication failed: no token bundle provided",
                remediation="Token bundle must be resolved from sandbox metadata",
            ),
        )

    return await service.execute(
        sandbox_url=sandbox_url,
        message=message,
        session_key=session_key,
        token_bundle=token_bundle or GatewayTokenBundle(current=""),
        workspace_id=workspace_id,
        agent_pack_id=agent_pack_id,
        run_id=run_id,
        sender_id=sender_id,
        session_id=session_id,
    )
