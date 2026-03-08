"""Sandbox gateway service for synchronous HTTP execution against in-sandbox runtime gateway.

This service provides:
- Health-first execution: polls /health before any execute request
- Bearer token authentication on both health and execute calls
- Typed errors for health failure, auth failure, timeout, upstream non-2xx responses
- Deterministic retry and timeout behavior
- Fail-closed semantics: never attempts execution when health/auth checks fail

The service is driven by SandboxRuntimeSpec from the integration spec file.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx

from src.config.settings import settings
from src.integrations.sandbox_runtime.spec import SandboxRuntimeSpec, load_runtime_spec


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
    status_code: int | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
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
    output: dict[str, Any] | None = None
    error: GatewayError | None = None

    def to_dict(self) -> dict[str, Any]:
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

    previous: str | None = None
    """Previous token valid during grace period rotation."""

    previous_expires_at: datetime | None = None
    """Expiry timestamp for previous token grace period."""

    def is_grace_token_valid(self) -> bool:
        """Check if the previous/grace token is still valid."""
        if not self.previous or not self.previous_expires_at:
            return False
        return datetime.utcnow() < self.previous_expires_at

    def get_effective_token(self, attempt: int = 0) -> str:
        """Get the token to use for authentication.

        On first attempt, uses current token. On retry and if
        grace token is still valid, may attempt with previous token.
        """
        if attempt == 0:
            return self.current
        if self.is_grace_token_valid():
            return self.previous
        return self.current


@dataclass
class HealthStatus:
    """Health check response from sandbox runtime gateway."""

    healthy: bool
    status: str | None = None
    details: dict[str, Any] | None = None


class SandboxGatewayService:
    """Gateway service for synchronous HTTP execution against in-sandbox runtime gateway.

    Implements:
    - Health-first execution: always polls /health before execute
    - Bearer token authentication (when spec requires bearer)
    - Fail-closed: execution is blocked if health/auth checks fail
    - Typed errors with remediation guidance
    - Deterministic retry and timeout behavior
    - Spec-driven: paths and port loaded from SandboxRuntimeSpec
    """

    DEFAULT_HEALTH_TIMEOUT = 10
    DEFAULT_HEALTH_RETRIES = 3
    DEFAULT_HEALTH_BACKOFF = 1.0
    DEFAULT_EXECUTE_TIMEOUT = 300
    DEFAULT_EXECUTE_RETRIES = 0

    def __init__(
        self,
        spec: SandboxRuntimeSpec | None = None,
        health_timeout: int | None = None,
        health_retries: int | None = None,
        health_backoff: float | None = None,
        execute_timeout: int | None = None,
        execute_retries: int | None = None,
    ):
        self._spec = spec or load_runtime_spec()

        gateway_config = getattr(settings, "SANDBOX_GATEWAY", None) or {}

        self.health_timeout = (
            health_timeout or gateway_config.get("HEALTH_TIMEOUT") or self.DEFAULT_HEALTH_TIMEOUT
        )
        self.health_retries = (
            health_retries or gateway_config.get("HEALTH_RETRIES") or self.DEFAULT_HEALTH_RETRIES
        )
        self.health_backoff = (
            health_backoff or gateway_config.get("HEALTH_BACKOFF") or self.DEFAULT_HEALTH_BACKOFF
        )
        self.execute_timeout = (
            execute_timeout
            or gateway_config.get("EXECUTE_TIMEOUT")
            or self.DEFAULT_EXECUTE_TIMEOUT
        )
        self.execute_retries = (
            execute_retries
            or gateway_config.get("EXECUTE_RETRIES")
            or self.DEFAULT_EXECUTE_RETRIES
        )

    @property
    def spec(self) -> SandboxRuntimeSpec:
        """Get the sandbox runtime spec used by this service."""
        return self._spec

    def _requires_auth(self) -> bool:
        return self._spec.auth.mode == "bearer"

    def _get_health_url(self, sandbox_url: str) -> str:
        base = sandbox_url.rstrip("/")
        path = self._spec.gateway.health_path
        return urljoin(base + "/", path.lstrip("/"))

    def _get_execute_url(self, sandbox_url: str) -> str:
        base = sandbox_url.rstrip("/")
        path = self._spec.gateway.execute_path
        return urljoin(base + "/", path.lstrip("/"))

    def _get_execute_candidate_urls(self, sandbox_url: str) -> list[str]:
        """Build candidate execute URLs with bidirectional compatibility fallback."""
        primary = self._get_execute_url(sandbox_url)

        if primary.endswith("/webhook"):
            fallback = urljoin(sandbox_url.rstrip("/") + "/", "execute")
        elif primary.endswith("/execute"):
            fallback = urljoin(sandbox_url.rstrip("/") + "/", "webhook")
        else:
            return [primary]

        if primary == fallback:
            return [primary]
        return [primary, fallback]

    def _get_auth_headers(
        self, token_bundle: GatewayTokenBundle, attempt: int = 0
    ) -> dict[str, str]:
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
        token_bundle: GatewayTokenBundle | None,
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with one-time auth fallback on 401/403."""
        headers = kwargs.pop("headers", {})
        base_headers = {"Content-Type": "application/json"}
        base_headers.update(headers)

        if token_bundle and self._requires_auth():
            auth_headers = self._get_auth_headers(token_bundle, attempt=0)
            base_headers.update(auth_headers)

        response = await client.request(method, url, headers=base_headers, **kwargs)

        if response.status_code in (401, 403):
            if token_bundle and self._requires_auth() and token_bundle.is_grace_token_valid():
                grace_headers = {"Content-Type": "application/json"}
                grace_headers.update(headers)
                grace_auth = self._get_auth_headers(token_bundle, attempt=1)
                grace_headers.update(grace_auth)
                response = await client.request(method, url, headers=grace_headers, **kwargs)

        return response

    async def check_health(
        self,
        sandbox_url: str,
        token_bundle: GatewayTokenBundle | None = None,
    ) -> HealthStatus:
        """Check health of sandbox runtime gateway."""
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
                        return HealthStatus(healthy=True, status="ok")
                elif response.status_code in (401, 403):
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
        token_bundle: GatewayTokenBundle | None = None,
    ) -> HealthStatus:
        """Poll health with retries and exponential backoff."""
        last_status = None

        for attempt in range(self.health_retries + 1):
            status = await self.check_health(sandbox_url, token_bundle)
            last_status = status

            if status.healthy:
                return status

            if attempt < self.health_retries:
                await asyncio.sleep(self.health_backoff * (2**attempt))

        return last_status or HealthStatus(healthy=False, status="unknown")

    def _transform_to_runtime_request(
        self,
        message: str,
        session_key: str,
        workspace_id: str | None = None,
        agent_pack_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        sender_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Transform Minerva envelope to sandbox runtime execute request format."""
        return {
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

    async def execute(
        self,
        sandbox_url: str,
        message: str,
        session_key: str,
        token_bundle: GatewayTokenBundle,
        workspace_id: str | None = None,
        agent_pack_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        sender_id: str | None = None,
        session_id: str | None = None,
    ) -> GatewayResult:
        """Execute request via gateway with health-first fail-closed flow."""
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

        # Step 2: Transform request
        runtime_request = self._transform_to_runtime_request(
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
                    headers: dict[str, str] = {"Content-Type": "application/json"}
                    if token_bundle and self._requires_auth():
                        headers = self._get_auth_headers(token_bundle, attempt=0)

                    for url_idx, execute_url in enumerate(execute_urls):
                        response = await client.post(
                            execute_url,
                            headers=headers,
                            json=runtime_request,
                        )

                        if response.status_code == 404 and url_idx == 0 and len(execute_urls) > 1:
                            continue

                        if (
                            response.status_code in (401, 403)
                            and not auth_fallback_attempted
                            and token_bundle
                            and self._requires_auth()
                            and token_bundle.is_grace_token_valid()
                        ):
                            auth_fallback_attempted = True
                            grace_headers = {"Content-Type": "application/json"}
                            grace_headers.update(self._get_auth_headers(token_bundle, attempt=1))
                            response = await client.post(
                                execute_url,
                                headers=grace_headers,
                                json=runtime_request,
                            )

                        if response.status_code == 200:
                            try:
                                data = response.json()
                                return GatewayResult(success=True, output=data)
                            except Exception:
                                return GatewayResult(
                                    success=False,
                                    error=GatewayError(
                                        error_type=GatewayErrorType.MALFORMED_RESPONSE,
                                        message="Failed to parse response",
                                        remediation="Contact support - response format may have changed.",
                                    ),
                                )
                        elif response.status_code in (401, 403):
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
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("error", "Unknown error")
                            except Exception:
                                error_msg = f"HTTP {response.status_code}"

                            last_error = GatewayError(
                                error_type=GatewayErrorType.UPSTREAM_ERROR,
                                message=error_msg,
                                status_code=response.status_code,
                                remediation="Check sandbox runtime gateway logs for details.",
                            )

                            if 400 <= response.status_code < 500:
                                return GatewayResult(success=False, error=last_error)

                            break

                except httpx.TimeoutException:
                    last_error = GatewayError(
                        error_type=GatewayErrorType.TIMEOUT,
                        message=f"Request timed out after {self.execute_timeout}s",
                        remediation="Increase SANDBOX_GATEWAY.EXECUTE_TIMEOUT or check sandbox performance.",
                    )
                except httpx.RequestError as e:
                    last_error = GatewayError(
                        error_type=GatewayErrorType.TRANSPORT_ERROR,
                        message=f"Transport error: {e!s}",
                        remediation="Check network connectivity to sandbox.",
                    )

                if attempt < self.execute_retries:
                    await asyncio.sleep(self.health_backoff * (2**attempt))

        return GatewayResult(success=False, error=last_error)


# Module-level convenience function
async def execute_via_gateway(
    sandbox_url: str,
    message: str,
    session_key: str,
    token_bundle: GatewayTokenBundle | None = None,
    workspace_id: str | None = None,
    agent_pack_id: str | None = None,
    run_id: str | None = None,
    sender_id: str | None = None,
    session_id: str | None = None,
    spec: SandboxRuntimeSpec | None = None,
) -> GatewayResult:
    """Execute a message via the sandbox runtime gateway.

    Convenience function that creates a gateway service and executes the request.
    """
    service = SandboxGatewayService(spec=spec)

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
