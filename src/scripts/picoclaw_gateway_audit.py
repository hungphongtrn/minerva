#!/usr/bin/env python3
"""Picoclaw gateway audit harness.

This script provides automated, repeatable auditing of Picoclaw gateway
capabilities using Daytona sandboxes or direct gateway URLs.

Usage:
    # Audit an existing gateway
    uv run python src/scripts/picoclaw_gateway_audit.py \
        --gateway-url https://gateway-xxx.daytona.run:18790 \
        --auth-token secret-token \
        --message "Hello world"

    # Audit via Daytona sandbox provisioning
    uv run python src/scripts/picoclaw_gateway_audit.py --daytona \
        --message "Hello world"

    # JSON output for CI/integration
    uv run python src/scripts/picoclaw_gateway_audit.py --daytona --json

Exit codes:
    0: Audit completed successfully
    1: Audit completed with failures
    2: Configuration error
    3: Unexpected error
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx


@dataclass
class AuditResult:
    """Result of a Picoclaw gateway audit."""

    success: bool
    mode: str  # 'daytona' or 'direct'
    health: Dict[str, Any] = field(default_factory=dict)
    execute: Dict[str, Any] = field(default_factory=dict)
    streaming_probe: Dict[str, Any] = field(default_factory=dict)
    continuity_wiring: Dict[str, Any] = field(default_factory=dict)
    sandbox_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "mode": self.mode,
            "health": self.health,
            "execute": self.execute,
            "streaming_probe": self.streaming_probe,
            "continuity_wiring": self.continuity_wiring,
            "sandbox_id": self.sandbox_id,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class PicoclawGatewayAuditor:
    """Auditor for Picoclaw gateway capabilities.

        Provisions disposable Daytona sandboxes and probes gateway endpoints
    to capture evidence about streaming, event, tool-call, and session
        continuity capabilities.
    """

    # Default timeouts
    HEALTH_TIMEOUT_SECONDS = 10
    EXECUTE_TIMEOUT_SECONDS = 30
    STREAM_PROBE_TIMEOUT_SECONDS = 5

    # Candidate streaming paths to probe
    STREAMING_CANDIDATE_PATHS = [
        "/events",
        "/stream",
        "/sse",
        "/ws",
        "/websocket",
        "/realtime",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        target: str = "us",
    ):
        """Initialize the auditor.

        Args:
            api_key: Daytona API key (or from DAYTONA_API_KEY env var)
            api_url: Daytona API URL (or from DAYTONA_API_URL env var)
            target: Target region for Daytona Cloud
        """
        self._api_key = (
            api_key if api_key is not None else os.environ.get("DAYTONA_API_KEY", "")
        )
        self._api_url = (
            api_url if api_url is not None else os.environ.get("DAYTONA_API_URL", "")
        )
        self._target = (
            target if target is not None else os.environ.get("DAYTONA_TARGET", "us")
        )

    async def audit_existing_gateway(
        self,
        gateway_url: str,
        auth_token: str,
        message: str,
        sender_id: str,
        session_id: str,
    ) -> AuditResult:
        """Audit an existing gateway URL directly.

        Args:
            gateway_url: Base URL of the Picoclaw gateway
            auth_token: Bearer token for authentication
            message: Test message to send
            sender_id: Sender identifier for continuity test
            session_id: Session identifier for continuity test

        Returns:
            AuditResult with all captured evidence
        """
        import time

        start_time = time.time()
        errors = []

        # Probe health endpoint
        health_result = await self._probe_health(gateway_url, auth_token)

        # Probe execute endpoint
        execute_result = await self._probe_execute(
            gateway_url, auth_token, message, sender_id, session_id
        )

        # Probe streaming candidates
        streaming_result = await self._probe_streaming_candidates(
            gateway_url, auth_token
        )

        # Capture continuity wiring info
        continuity_result = self._capture_continuity_wiring(
            sender_id, session_id, execute_result.get("request_transformed")
        )

        # Determine overall success
        success = health_result.get("accessible", False)

        duration = time.time() - start_time

        return AuditResult(
            success=success,
            mode="direct",
            health=health_result,
            execute=execute_result,
            streaming_probe=streaming_result,
            continuity_wiring=continuity_result,
            sandbox_id=None,
            errors=errors,
            duration_seconds=duration,
        )

    async def audit_daytona_sandbox(
        self,
        message: str,
        sender_id: str,
        session_id: str,
        workspace_id: Optional[str] = None,
    ) -> AuditResult:
        """Audit by provisioning a disposable Daytona sandbox.

        Args:
            message: Test message to send
            sender_id: Sender identifier for continuity test
            session_id: Session identifier for continuity test
            workspace_id: Optional workspace ID for sandbox labeling

        Returns:
            AuditResult with all captured evidence
        """
        import time

        start_time = time.time()
        errors = []
        sandbox_id = None

        try:
            # Import here to avoid dependency issues when not using Daytona mode
            from src.infrastructure.sandbox.providers.daytona import (
                DaytonaSandboxProvider,
            )
            from src.infrastructure.sandbox.providers.base import (
                SandboxConfig,
                SandboxRef,
            )
            from src.services.picoclaw_bridge_service import (
                PicoclawBridgeService,
                BridgeTokenBundle,
            )

            # Generate deterministic auth token for this audit
            auth_token = f"audit-{uuid.uuid4().hex[:16]}"

            # Create provider
            provider = DaytonaSandboxProvider(
                api_key=self._api_key,
                api_url=self._api_url,
                target=self._target,
            )

            # Build sandbox config with runtime bridge config
            config = SandboxConfig(
                workspace_id=uuid.uuid4(),
                external_user_id=f"audit-{sender_id}",
                session_id=session_id,
                runtime_bridge_config={
                    "bridge": {
                        "auth_token": auth_token,
                        "enabled": True,
                    }
                },
            )

            # Provision sandbox
            try:
                sandbox_info = await provider.provision_sandbox(config)
                sandbox_id = sandbox_info.ref.provider_ref
            except Exception as e:
                errors.append(f"Failed to provision sandbox: {e}")
                return AuditResult(
                    success=False,
                    mode="daytona",
                    errors=errors,
                    duration_seconds=time.time() - start_time,
                )

            # Extract gateway URL from sandbox metadata
            gateway_url = sandbox_info.ref.metadata.get("gateway_url")
            if not gateway_url:
                errors.append("Sandbox provisioned but no gateway URL in metadata")
                return AuditResult(
                    success=False,
                    mode="daytona",
                    sandbox_id=sandbox_id,
                    errors=errors,
                    duration_seconds=time.time() - start_time,
                )

            # Run probes
            health_result = await self._probe_health(gateway_url, auth_token)

            # For execute, use the bridge service with token bundle
            execute_result = await self._probe_execute_via_bridge(
                gateway_url, auth_token, message, sender_id, session_id
            )

            streaming_result = await self._probe_streaming_candidates(
                gateway_url, auth_token
            )

            continuity_result = self._capture_continuity_wiring(
                sender_id, session_id, execute_result.get("request_transformed")
            )

            success = health_result.get("accessible", False)
            duration = time.time() - start_time

            return AuditResult(
                success=success,
                mode="daytona",
                health=health_result,
                execute=execute_result,
                streaming_probe=streaming_result,
                continuity_wiring=continuity_result,
                sandbox_id=sandbox_id,
                errors=errors,
                duration_seconds=duration,
            )

        finally:
            # Always clean up the sandbox
            if sandbox_id:
                try:
                    from src.infrastructure.sandbox.providers.daytona import (
                        DaytonaSandboxProvider,
                    )
                    from src.infrastructure.sandbox.providers.base import SandboxRef

                    provider = DaytonaSandboxProvider(
                        api_key=self._api_key,
                        api_url=self._api_url,
                        target=self._target,
                    )

                    ref = SandboxRef(
                        provider_ref=sandbox_id,
                        profile="daytona",
                    )
                    await provider.stop_sandbox(ref)
                except Exception as e:
                    # Don't fail the audit due to cleanup issues
                    errors.append(f"Cleanup warning: {e}")

    async def _probe_health(self, gateway_url: str, auth_token: str) -> Dict[str, Any]:
        """Probe the /health endpoint.

        Args:
            gateway_url: Base URL of the gateway
            auth_token: Bearer token for authentication

        Returns:
            Dict with status_code, accessible flag, and parsed JSON (best-effort)
        """
        health_url = urljoin(gateway_url.rstrip("/") + "/", "health")

        async with httpx.AsyncClient(timeout=self.HEALTH_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(
                    health_url,
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Accept": "application/json",
                    },
                )

                result = {
                    "status_code": response.status_code,
                    "accessible": response.status_code == 200,
                    "url": health_url,
                }

                # Best-effort JSON parsing
                try:
                    result["body"] = response.json()
                except Exception:
                    result["body"] = response.text[:500]  # Truncated text

                return result

            except httpx.TimeoutException:
                return {
                    "status_code": None,
                    "accessible": False,
                    "url": health_url,
                    "error": "timeout",
                }
            except httpx.RequestError as e:
                return {
                    "status_code": None,
                    "accessible": False,
                    "url": health_url,
                    "error": str(e),
                }

    async def _probe_execute(
        self,
        gateway_url: str,
        auth_token: str,
        message: str,
        sender_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Probe the /bridge/execute endpoint directly.

        Args:
            gateway_url: Base URL of the gateway
            auth_token: Bearer token for authentication
            message: Test message to send
            sender_id: Sender identifier
            session_id: Session identifier

        Returns:
            Dict with status_code and response details
        """
        execute_url = urljoin(gateway_url.rstrip("/") + "/", "bridge/execute")

        # Generate deterministic session key
        session_key = f"minerva:audit:{uuid.uuid4().hex[:8]}"

        # Build request payload (Picoclaw format)
        request_payload = {
            "channel": "bridge",
            "sender_id": sender_id,
            "chat_id": session_key,
            "content": message,
            "session_key": session_key,
            "session_id": session_id,
            "metadata": {
                "audit": True,
                "probe": True,
            },
        }

        async with httpx.AsyncClient(timeout=self.EXECUTE_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(
                    execute_url,
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )

                result = {
                    "status_code": response.status_code,
                    "url": execute_url,
                    "session_key": session_key,
                    "request_transformed": request_payload,
                }

                # Best-effort JSON parsing
                try:
                    result["body"] = response.json()
                except Exception:
                    result["body"] = response.text[:500]

                return result

            except httpx.TimeoutException:
                return {
                    "status_code": None,
                    "url": execute_url,
                    "session_key": session_key,
                    "request_transformed": request_payload,
                    "error": "timeout",
                }
            except httpx.RequestError as e:
                return {
                    "status_code": None,
                    "url": execute_url,
                    "session_key": session_key,
                    "request_transformed": request_payload,
                    "error": str(e),
                }

    async def _probe_execute_via_bridge(
        self,
        gateway_url: str,
        auth_token: str,
        message: str,
        sender_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Probe execute using the PicoclawBridgeService.

        Args:
            gateway_url: Base URL of the gateway
            auth_token: Bearer token for authentication
            message: Test message to send
            sender_id: Sender identifier
            session_id: Session identifier

        Returns:
            Dict with execution results
        """
        from src.services.picoclaw_bridge_service import (
            PicoclawBridgeService,
            BridgeTokenBundle,
        )

        service = PicoclawBridgeService()
        session_key = f"minerva:audit:{uuid.uuid4().hex[:8]}"
        token_bundle = BridgeTokenBundle(current=auth_token)

        result = await service.execute(
            sandbox_url=gateway_url,
            message=message,
            session_key=session_key,
            token_bundle=token_bundle,
            sender_id=sender_id,
            session_id=session_id,
            metadata={"audit": True, "probe": True},
        )

        return {
            "status_code": 200 if result.success else None,
            "url": urljoin(gateway_url.rstrip("/") + "/", "bridge/execute"),
            "session_key": session_key,
            "request_transformed": {
                "channel": "bridge",
                "sender_id": sender_id,
                "session_key": session_key,
                "session_id": session_id,
                "content": message,
            },
            "bridge_result": result.to_dict(),
            "success": result.success,
        }

    async def _probe_streaming_candidates(
        self, gateway_url: str, auth_token: str
    ) -> Dict[str, Any]:
        """Probe candidate streaming/event paths.

        Args:
            gateway_url: Base URL of the gateway
            auth_token: Bearer token for authentication

        Returns:
            Dict mapping paths to probe results
        """
        results = {}
        results["candidate_paths"] = self.STREAMING_CANDIDATE_PATHS
        results["probes"] = {}

        async with httpx.AsyncClient(
            timeout=self.STREAM_PROBE_TIMEOUT_SECONDS
        ) as client:
            for path in self.STREAMING_CANDIDATE_PATHS:
                url = urljoin(gateway_url.rstrip("/") + "/", path.lstrip("/"))

                try:
                    response = await client.get(
                        url,
                        headers={
                            "Authorization": f"Bearer {auth_token}",
                            "Accept": "text/event-stream, application/json",
                        },
                    )

                    results["probes"][path] = {
                        "status_code": response.status_code,
                        "accessible": response.status_code < 400,
                        "error": None,
                    }

                except httpx.TimeoutException:
                    results["probes"][path] = {
                        "status_code": None,
                        "accessible": False,
                        "error": "timeout",
                    }
                except httpx.RequestError as e:
                    results["probes"][path] = {
                        "status_code": None,
                        "accessible": False,
                        "error": str(e),
                    }

        # Determine if any streaming endpoints exist
        results["any_streaming_available"] = any(
            p.get("accessible", False) for p in results["probes"].values()
        )

        return results

    def _capture_continuity_wiring(
        self,
        sender_id: str,
        session_id: str,
        request_transformed: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Capture session continuity wiring evidence.

        Args:
            sender_id: Original sender_id used
            session_id: Original session_id used
            request_transformed: The transformed request dict (from bridge service)

        Returns:
            Dict with continuity wiring evidence
        """
        return {
            "original_sender_id": sender_id,
            "original_session_id": session_id,
            "request_transformed": request_transformed,
            "sender_id_forwarded": request_transformed.get("sender_id") == sender_id
            if request_transformed
            else None,
            "session_id_forwarded": request_transformed.get("session_id") == session_id
            if request_transformed
            else None,
        }

    async def run(
        self,
        daytona_mode: bool = False,
        gateway_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        message: str = "Hello from Picoclaw gateway audit",
        sender_id: str = "minerva-audit",
        session_id: str = "audit-session",
    ) -> AuditResult:
        """Run the audit with specified mode.

        Args:
            daytona_mode: If True, provision a Daytona sandbox
            gateway_url: Direct gateway URL (for non-Daytona mode)
            auth_token: Auth token for gateway access
            message: Test message to send
            sender_id: Sender identifier for continuity test
            session_id: Session identifier for continuity test

        Returns:
            AuditResult with all evidence
        """
        if daytona_mode:
            return await self.audit_daytona_sandbox(
                message=message,
                sender_id=sender_id,
                session_id=session_id,
            )
        else:
            if not gateway_url:
                raise ValueError("gateway_url required for direct mode")
            if not auth_token:
                raise ValueError("auth_token required for direct mode")

            return await self.audit_existing_gateway(
                gateway_url=gateway_url,
                auth_token=auth_token,
                message=message,
                sender_id=sender_id,
                session_id=session_id,
            )


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="picoclaw_gateway_audit",
        description="Audit Picoclaw gateway capabilities",
        epilog="""
Environment Variables:
    DAYTONA_API_KEY         Daytona API authentication key (required for --daytona)
    DAYTONA_API_URL         Daytona API endpoint (optional, uses Cloud by default)
    DAYTONA_TARGET          Target region (default: us)

Examples:
    # Audit via Daytona sandbox provisioning
    uv run python %(prog)s --daytona --message "Test message"

    # Audit existing gateway directly
    uv run python %(prog)s --gateway-url https://gateway-xxx.daytona.run:18790 \
        --auth-token secret --message "Test message"

    # JSON output for CI
    uv run python %(prog)s --daytona --json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--daytona",
        action="store_true",
        help="Provision a Daytona sandbox for the audit",
    )

    parser.add_argument(
        "--gateway-url",
        help="Gateway URL for direct audit (not --daytona mode)",
    )

    parser.add_argument(
        "--auth-token",
        help="Auth token for gateway access (not --daytona mode)",
    )

    parser.add_argument(
        "--message",
        default="Hello from Picoclaw gateway audit",
        help="Test message to send (default: %(default)s)",
    )

    parser.add_argument(
        "--sender-id",
        default="minerva-audit",
        help="Sender identifier for continuity test (default: %(default)s)",
    )

    parser.add_argument(
        "--session-id",
        default="audit-session",
        help="Session identifier for continuity test (default: %(default)s)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-readable text",
    )

    parser.add_argument(
        "--target",
        default="us",
        help="Daytona target region (default: %(default)s)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    return parser


async def main_async() -> int:
    """Async main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Validate arguments
    if not args.daytona:
        if not args.gateway_url:
            print(
                "Error: --gateway-url required when not using --daytona mode",
                file=sys.stderr,
            )
            return 2
        if not args.auth_token:
            print(
                "Error: --auth-token required when not using --daytona mode",
                file=sys.stderr,
            )
            return 2

    # Check Daytona credentials if using Daytona mode
    if args.daytona:
        api_key = os.environ.get("DAYTONA_API_KEY", "")
        api_url = os.environ.get("DAYTONA_API_URL", "")

        if not api_key and (not api_url or "daytona.io" in api_url):
            if args.json:
                print(
                    json.dumps(
                        {
                            "success": False,
                            "errors": [
                                "DAYTONA_API_KEY environment variable is required for --daytona mode"
                            ],
                            "remediation": "Set DAYTONA_API_KEY environment variable",
                        }
                    )
                )
            else:
                print(
                    "Error: DAYTONA_API_KEY environment variable is required for --daytona mode",
                    file=sys.stderr,
                )
                print(
                    "Set it with: export DAYTONA_API_KEY='your-api-key'",
                    file=sys.stderr,
                )
            return 2

    # Run audit
    auditor = PicoclawGatewayAuditor(target=args.target)

    try:
        result = await auditor.run(
            daytona_mode=args.daytona,
            gateway_url=args.gateway_url,
            auth_token=args.auth_token,
            message=args.message,
            sender_id=args.sender_id,
            session_id=args.session_id,
        )

        # Output results
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n{'=' * 60}")
            print("Picoclaw Gateway Audit")
            print(f"{'=' * 60}")
            print(f"Mode: {result.mode}")
            if result.sandbox_id:
                print(f"Sandbox ID: {result.sandbox_id}")
            print(f"Duration: {result.duration_seconds:.2f}s")
            print(f"{'=' * 60}")

            print("\nHealth Check:")
            health = result.health
            if health.get("accessible"):
                print(f"  ✓ Accessible (HTTP {health.get('status_code')})")
            else:
                print(f"  ✗ Not accessible (HTTP {health.get('status_code')})")
                if health.get("error"):
                    print(f"    Error: {health.get('error')}")

            print("\nExecute Probe:")
            execute = result.execute
            print(f"  URL: {execute.get('url', 'N/A')}")
            print(f"  Session Key: {execute.get('session_key', 'N/A')}")
            if execute.get("success"):
                print(f"  ✓ Success")
            elif execute.get("status_code"):
                print(f"  Status: HTTP {execute.get('status_code')}")
            if execute.get("error"):
                print(f"  Error: {execute.get('error')}")

            print("\nStreaming Probe:")
            streaming = result.streaming_probe
            print(f"  Candidate Paths: {len(streaming.get('candidate_paths', []))}")
            any_available = streaming.get("any_streaming_available", False)
            if any_available:
                print(f"  ✓ At least one streaming endpoint accessible")
            else:
                print(f"  ✗ No streaming endpoints accessible")

            print("\nContinuity Wiring:")
            continuity = result.continuity_wiring
            print(f"  Sender ID: {continuity.get('original_sender_id')}")
            print(f"  Session ID: {continuity.get('original_session_id')}")
            if continuity.get("sender_id_forwarded"):
                print(f"  ✓ Sender ID forwarded correctly")
            else:
                print(f"  ✗ Sender ID not forwarded")
            if continuity.get("session_id_forwarded"):
                print(f"  ✓ Session ID forwarded correctly")
            else:
                print(f"  ✗ Session ID not forwarded")

            if result.errors:
                print("\nErrors:")
                for error in result.errors:
                    print(f"  - {error}")

            if result.success:
                print("\n✓ AUDIT PASSED")
            else:
                print("\n✗ AUDIT FAILED")

        return 0 if result.success else 1

    except Exception as e:
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "errors": [str(e)],
                        "remediation": "Check configuration and try again",
                    }
                )
            )
        else:
            print(f"\n✗ AUDIT ERROR: {e}", file=sys.stderr)
        return 3


def main() -> int:
    """Main entry point."""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
