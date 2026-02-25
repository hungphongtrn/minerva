"""Picoclaw bridge service for synchronous HTTP execution against in-sandbox Picoclaw gateway.

This service provides:
- Health-first execution: polls /health before any execute request
- Bearer token authentication on both health and execute calls
- Typed errors for health failure, auth failure, timeout, upstream non-2xx responses
- Deterministic retry and timeout behavior
- Fail-closed semantics: never attempts execution when health/auth checks fail
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional
import httpx
from urllib.parse import urljoin

from src.config.settings import settings


class BridgeErrorType(str, Enum):
    """Typed error categories for bridge failures."""

    HEALTH_CHECK_FAILED = "health_check_failed"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    UPSTREAM_ERROR = "upstream_error"
    MALFORMED_RESPONSE = "malformed_response"


@dataclass
class BridgeError:
    """Structured error from bridge operations."""

    error_type: BridgeErrorType
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
class BridgeResult:
    """Result of a bridge execution."""

    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[BridgeError] = None

    def to_dict(self) -> Dict[str, Any]:
        if self.success:
            return {"success": True, "output": self.output}
        return {"success": False, "error": self.error.to_dict() if self.error else None}


@dataclass
class HealthStatus:
    """Health check response from Picoclaw gateway."""

    healthy: bool
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class PicoclawBridgeService:
    """Bridge service for synchronous HTTP execution against in-sandbox Picoclaw gateway.

    This service implements:
    - Health-first execution: always polls /health before execute
    - Bearer token authentication
    - Fail-closed: execution is blocked if health/auth checks fail
    - Typed errors with remediation guidance
    - Deterministic retry and timeout behavior
    """

    # Default configuration values
    DEFAULT_HEALTH_TIMEOUT = 10  # seconds
    DEFAULT_HEALTH_RETRIES = 3
    DEFAULT_HEALTH_BACKOFF = 1.0  # seconds
    DEFAULT_EXECUTE_TIMEOUT = 300  # 5 minutes
    DEFAULT_EXECUTE_RETRIES = 0  # No retries for execute by default (synchronous phase)

    def __init__(
        self,
        health_timeout: Optional[int] = None,
        health_retries: Optional[int] = None,
        health_backoff: Optional[float] = None,
        execute_timeout: Optional[int] = None,
        execute_retries: Optional[int] = None,
    ):
        """Initialize the bridge service.

        Args:
            health_timeout: Timeout for health check requests in seconds
            health_retries: Number of retries for health check failures
            health_backoff: Backoff delay between health check retries
            execute_timeout: Timeout for execute requests in seconds
            execute_retries: Number of retries for execute failures
        """
        # Load from settings with fallbacks to defaults
        picoclaw_config = getattr(settings, "PICOCLAW_BRIDGE", None) or {}

        self.health_timeout = (
            health_timeout
            or picoclaw_config.get("HEALTH_TIMEOUT")
            or self.DEFAULT_HEALTH_TIMEOUT
        )
        self.health_retries = (
            health_retries
            or picoclaw_config.get("HEALTH_RETRIES")
            or self.DEFAULT_HEALTH_RETRIES
        )
        self.health_backoff = (
            health_backoff
            or picoclaw_config.get("HEALTH_BACKOFF")
            or self.DEFAULT_HEALTH_BACKOFF
        )
        self.execute_timeout = (
            execute_timeout
            or picoclaw_config.get("EXECUTE_TIMEOUT")
            or self.DEFAULT_EXECUTE_TIMEOUT
        )
        self.execute_retries = (
            execute_retries
            or picoclaw_config.get("EXECUTE_RETRIES")
            or self.DEFAULT_EXECUTE_RETRIES
        )

    def _get_auth_token(self, sandbox_url: str) -> str:
        """Get bearer token for sandbox authentication.

        Token is retrieved from environment or settings.
        In production, this would be per-sandbox scoped.

        Args:
            sandbox_url: The sandbox URL (used for token resolution)

        Returns:
            Bearer token string
        """
        # TODO: Per-sandbox token resolution
        # For now, use environment variable
        token = getattr(settings, "PICOCLAW_BRIDGE_TOKEN", None)
        if not token:
            # Fallback for development
            token = "dev-token"
        return token

    def _get_auth_headers(self, sandbox_url: str) -> Dict[str, str]:
        """Get authentication headers for requests.

        Args:
            sandbox_url: The sandbox URL

        Returns:
            Dictionary of headers including Authorization
        """
        token = self._get_auth_token(sandbox_url)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def check_health(self, sandbox_url: str) -> HealthStatus:
        """Check health of Picoclaw gateway in sandbox.

        Args:
            sandbox_url: Base URL of the sandbox gateway

        Returns:
            HealthStatus with healthy flag and details
        """
        health_url = urljoin(sandbox_url.rstrip("/") + "/", "health")

        async with httpx.AsyncClient(timeout=self.health_timeout) as client:
            try:
                response = await client.get(
                    health_url, headers=self._get_auth_headers(sandbox_url)
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
                return HealthStatus(
                    healthy=False, status="error", details={"error": str(e)}
                )

    async def poll_health(self, sandbox_url: str) -> HealthStatus:
        """Poll health with retries and exponential backoff.

        This implements deterministic retry behavior:
        - Always polls /health before execution
        - Retries on transient failures with bounded backoff
        - Fails-closed: returns unhealthy status after exhausting retries

        Args:
            sandbox_url: Base URL of the sandbox gateway

        Returns:
            HealthStatus with final healthy/unhealthy state
        """
        last_status = None

        for attempt in range(self.health_retries + 1):
            status = await self.check_health(sandbox_url)
            last_status = status

            if status.healthy:
                return status

            # Wait before retry with exponential backoff
            if attempt < self.health_retries:
                await asyncio.sleep(self.health_backoff * (2**attempt))

        # Return the last status after exhausting retries
        return last_status or HealthStatus(healthy=False, status="unknown")

    def _transform_to_picoclaw_request(
        self,
        message: str,
        session_key: str,
        workspace_id: Optional[str] = None,
        agent_pack_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Transform Minerva envelope to Picoclaw InboundMessage format.

        Args:
            message: The message content from Minerva request
            session_key: Session key for continuity
            workspace_id: Workspace ID for scoping
            agent_pack_id: Agent pack ID if bound
            run_id: Run ID for tracing
            metadata: Additional metadata

        Returns:
            Picoclaw-format request dictionary
        """
        return {
            "channel": "bridge",
            "sender_id": "minerva",
            "chat_id": session_key,
            "content": message,
            "session_key": session_key,
            "metadata": {
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
        workspace_id: Optional[str] = None,
        agent_pack_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BridgeResult:
        """Execute request via bridge with health-first fail-closed flow.

        This method:
        1. Polls /health before any execution (fail-closed)
        2. Attaches bearer token to execution request
        3. Returns typed errors for all failure modes
        4. Respects timeout and retry configuration

        Args:
            sandbox_url: Base URL of the sandbox gateway
            message: The message to send to Picoclaw
            session_key: Session key for continuity
            workspace_id: Workspace ID for scoping
            agent_pack_id: Agent pack ID if bound
            run_id: Run ID for tracing
            metadata: Additional metadata

        Returns:
            BridgeResult with success/output or error details
        """
        # Step 1: Health check (fail-closed)
        health = await self.poll_health(sandbox_url)

        if not health.healthy:
            error_type = BridgeErrorType.HEALTH_CHECK_FAILED
            if health.status == "unauthorized":
                error_type = BridgeErrorType.AUTH_FAILED

            return BridgeResult(
                success=False,
                error=BridgeError(
                    error_type=error_type,
                    message=f"Health check failed: {health.status}",
                    remediation="Sandbox may be unhealthy or unreachable. Try again later or reprovision.",
                ),
            )

        # Step 2: Transform request to Picoclaw format
        picoclaw_request = self._transform_to_picoclaw_request(
            message=message,
            session_key=session_key,
            workspace_id=workspace_id,
            agent_pack_id=agent_pack_id,
            run_id=run_id,
            metadata=metadata,
        )

        # Step 3: Execute request with retries
        execute_url = urljoin(sandbox_url.rstrip("/") + "/", "bridge/execute")
        last_error = None

        for attempt in range(self.execute_retries + 1):
            async with httpx.AsyncClient(timeout=self.execute_timeout) as client:
                try:
                    response = await client.post(
                        execute_url,
                        headers=self._get_auth_headers(sandbox_url),
                        json=picoclaw_request,
                    )

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            return BridgeResult(success=True, output=data)
                        except Exception as e:
                            return BridgeResult(
                                success=False,
                                error=BridgeError(
                                    error_type=BridgeErrorType.MALFORMED_RESPONSE,
                                    message=f"Failed to parse response: {str(e)}",
                                    remediation="Contact support - response format may have changed.",
                                ),
                            )
                    elif response.status_code == 401 or response.status_code == 403:
                        return BridgeResult(
                            success=False,
                            error=BridgeError(
                                error_type=BridgeErrorType.AUTH_FAILED,
                                message="Authentication failed",
                                status_code=response.status_code,
                                remediation="Check bridge token configuration.",
                            ),
                        )
                    else:
                        # Non-2xx response from upstream
                        try:
                            error_data = response.json()
                            error_msg = error_data.get("error", "Unknown error")
                        except Exception:
                            error_msg = f"HTTP {response.status_code}"

                        last_error = BridgeError(
                            error_type=BridgeErrorType.UPSTREAM_ERROR,
                            message=error_msg,
                            status_code=response.status_code,
                            remediation="Check Picoclaw gateway logs for details.",
                        )

                        # Don't retry on 4xx errors
                        if 400 <= response.status_code < 500:
                            break

                except httpx.TimeoutException:
                    last_error = BridgeError(
                        error_type=BridgeErrorType.TIMEOUT,
                        message=f"Request timed out after {self.execute_timeout}s",
                        remediation="Increase PICOCLAW_BRIDGE.EXECUTE_TIMEOUT or check sandbox performance.",
                    )
                except httpx.RequestError as e:
                    last_error = BridgeError(
                        error_type=BridgeErrorType.TRANSPORT_ERROR,
                        message=f"Transport error: {str(e)}",
                        remediation="Check network connectivity to sandbox.",
                    )

                # Wait before retry with backoff
                if attempt < self.execute_retries:
                    await asyncio.sleep(self.health_backoff * (2**attempt))

        # Return last error if all retries exhausted
        return BridgeResult(success=False, error=last_error)


# Module-level convenience function
async def execute_via_bridge(
    sandbox_url: str,
    message: str,
    session_key: str,
    workspace_id: Optional[str] = None,
    agent_pack_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> BridgeResult:
    """Execute a message via the Picoclaw bridge.

    Convenience function that creates a bridge service and executes the request.

    Args:
        sandbox_url: Base URL of the sandbox gateway
        message: The message to send
        session_key: Session key for continuity
        workspace_id: Workspace ID for scoping
        agent_pack_id: Agent pack ID if bound
        run_id: Run ID for tracing

    Returns:
        BridgeResult with execution outcome
    """
    service = PicoclawBridgeService()
    return await service.execute(
        sandbox_url=sandbox_url,
        message=message,
        session_key=session_key,
        workspace_id=workspace_id,
        agent_pack_id=agent_pack_id,
        run_id=run_id,
    )
