#!/usr/bin/env python3
"""Zeroclaw webhook E2E probe for multi-user -> multi-sandbox validation.

This script validates the complete Zeroclaw execution path:
1. POST /runs with distinct X-User-ID values
2. SSE stream consumption until completion
3. Database assertion: 2 sandbox_instances with different provider_ref

Usage (dry-run - default, no credentials needed):
    uv run python src/scripts/zeroclaw_webhook_e2e.py --dry-run

Usage (live execution - requires running server and DB):
    uv run python src/scripts/zeroclaw_webhook_e2e.py --run --base-url http://localhost:8000

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (required for --run mode)
    MINERVA_WORKSPACE_ID: Workspace ID for routing (default: test-workspace)

Exit Codes:
    0: All checks passed
    1: Assertion failure or verification error
    2: Configuration error (missing env vars)
    3: Unexpected error
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Required environment variables for live execution
REQUIRED_ENV_VARS = ["DATABASE_URL"]

# Default configuration
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_WORKSPACE_ID = "test-workspace"
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass
class ProbeResult:
    """Result of E2E probe execution."""

    success: bool
    user_ids: List[str] = field(default_factory=list)
    sandbox_ids: List[str] = field(default_factory=list)
    provider_refs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "user_ids": self.user_ids,
            "sandbox_ids": self.sandbox_ids,
            "provider_refs": self.provider_refs,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class ZeroclawWebhookE2EProbe:
    """E2E probe for Zeroclaw multi-user validation.

    Validates that distinct X-User-ID values result in distinct sandbox
    instances with different provider_ref values.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the E2E probe.

        Args:
            base_url: Base URL of the Minerva API server
            workspace_id: Workspace ID for routing
            timeout_seconds: Timeout for each run request
        """
        self._base_url = base_url.rstrip("/")
        self._workspace_id = workspace_id
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._client.aclose()

    async def check_server_ready(self) -> bool:
        """Check if server is ready via /ready endpoint.

        Returns:
            True if server reports ready
        """
        try:
            response = await self._client.get(f"{self._base_url}/ready")
            return response.status_code == 200
        except Exception:
            return False

    async def send_run_request(
        self,
        user_id: str,
        session_id: str,
        message: str = "Hello, Zeroclaw!",
    ) -> Dict[str, Any]:
        """Send a run request and collect SSE events.

        Args:
            user_id: X-User-ID header value
            session_id: X-Session-ID header value
            message: Message payload

        Returns:
            Dictionary with events and final status
        """
        run_id = str(uuid4())
        headers = {
            "X-User-ID": user_id,
            "X-Session-ID": session_id,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        payload = {"message": message}
        events = []

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/runs",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "events": events,
                        "run_id": run_id,
                    }

                # Extract run_id from headers if available
                run_id = response.headers.get("X-Run-ID", run_id)

                # Read SSE stream
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            events.append(data)

                            # Check for terminal events
                            if data.get("event") in ("completed", "failed"):
                                break
                        except json.JSONDecodeError:
                            continue

            return {
                "success": True,
                "events": events,
                "run_id": run_id,
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "error": f"Timeout after {self._timeout_seconds}s",
                "events": events,
                "run_id": run_id,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "events": events,
                "run_id": run_id,
            }

    def query_sandboxes(
        self,
        user_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Query database for sandbox instances by user IDs.

        Args:
            user_ids: List of external_user_id values to query

        Returns:
            List of sandbox instance records
        """
        from src.config.settings import get_database_url

        database_url = get_database_url()
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=engine)

        results = []
        with SessionLocal() as session:
            # Query for sandboxes matching the user IDs in this workspace
            query = text("""
                SELECT id, external_user_id, provider_ref, status, created_at
                FROM sandbox_instances
                WHERE external_user_id = ANY(:user_ids)
                AND workspace_id = :workspace_id
                ORDER BY created_at DESC
            """)

            result = session.execute(
                query,
                {
                    "user_ids": user_ids,
                    "workspace_id": self._workspace_id,
                },
            )

            for row in result:
                results.append(
                    {
                        "id": str(row.id),
                        "external_user_id": row.external_user_id,
                        "provider_ref": row.provider_ref,
                        "status": row.status,
                        "created_at": row.created_at.isoformat()
                        if row.created_at
                        else None,
                    }
                )

        return results

    async def run_probe(self) -> ProbeResult:
        """Execute the full E2E probe.

        Returns:
            ProbeResult with success status and sandbox information
        """
        import time

        start_time = time.time()
        errors = []
        user_ids = []
        sandbox_ids = []
        provider_refs = []

        # Generate two distinct user IDs
        user_id_1 = f"e2e-test-user-{uuid4().hex[:8]}"
        user_id_2 = f"e2e-test-user-{uuid4().hex[:8]}"
        user_ids = [user_id_1, user_id_2]

        # Fixed session IDs
        session_id_1 = f"session-{uuid4().hex[:8]}"
        session_id_2 = f"session-{uuid4().hex[:8]}"

        try:
            # Check server is ready
            if not await self.check_server_ready():
                errors.append(f"Server not ready at {self._base_url}/ready")
                return ProbeResult(
                    success=False,
                    user_ids=user_ids,
                    errors=errors,
                    duration_seconds=time.time() - start_time,
                )

            # Send run requests concurrently
            results = await asyncio.gather(
                self.send_run_request(user_id_1, session_id_1),
                self.send_run_request(user_id_2, session_id_2),
            )

            # Check for request failures
            for i, result in enumerate(results):
                if not result["success"]:
                    errors.append(
                        f"User {i + 1} ({user_ids[i]}): {result.get('error', 'Unknown error')}"
                    )

            if errors:
                return ProbeResult(
                    success=False,
                    user_ids=user_ids,
                    errors=errors,
                    duration_seconds=time.time() - start_time,
                )

            # Query database for sandboxes
            sandboxes = self.query_sandboxes(user_ids)

            # Validate we have exactly 2 sandboxes
            if len(sandboxes) != 2:
                errors.append(f"Expected 2 sandbox instances, found {len(sandboxes)}")

            # Validate provider_refs differ
            if len(sandboxes) >= 2:
                provider_refs = [s["provider_ref"] for s in sandboxes]
                sandbox_ids = [s["id"] for s in sandboxes]

                if len(set(provider_refs)) != len(provider_refs):
                    errors.append(
                        f"Sandbox provider_refs should be unique but found: {provider_refs}"
                    )

            # Validate each user has their own sandbox
            found_user_ids = {s["external_user_id"] for s in sandboxes}
            for uid in user_ids:
                if uid not in found_user_ids:
                    errors.append(f"No sandbox found for user {uid}")

            duration = time.time() - start_time

            return ProbeResult(
                success=len(errors) == 0,
                user_ids=user_ids,
                sandbox_ids=sandbox_ids,
                provider_refs=provider_refs,
                errors=errors,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            errors.append(f"Unexpected error: {e}")
            return ProbeResult(
                success=False,
                user_ids=user_ids,
                errors=errors,
                duration_seconds=duration,
            )


def check_prerequisites() -> List[str]:
    """Check local prerequisites for running the probe.

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors = []

    # Check imports work
    try:
        import httpx
        import sqlalchemy
        from src.config.settings import get_database_url
        from src.services.agent_pack_validation import AgentPackValidationService
    except ImportError as e:
        errors.append(f"Import error: {e}")
        return errors

    # Check agent pack exists
    pack_path = "src/agent_packs/zeroclaw"
    if not os.path.exists(pack_path):
        errors.append(f"Agent pack not found: {pack_path}")
    else:
        validation_service = AgentPackValidationService()
        report = validation_service.validate(pack_path)
        if not report.is_valid:
            errors.append(f"Agent pack validation failed: {report.to_json()}")

    return errors


def print_dry_run_info():
    """Print dry-run information and required setup."""
    print("=" * 60)
    print("Zeroclaw Webhook E2E Probe - Dry Run")
    print("=" * 60)
    print()
    print("Prerequisites check:")

    errors = check_prerequisites()
    if errors:
        for error in errors:
            print(f"  ✗ {error}")
        print()
        print("Status: FAILED - Fix prerequisites before running live probe")
        return False
    else:
        print("  ✓ All imports successful")
        print("  ✓ Agent pack validates")
        print()
        print("Status: READY")
        print()
        print("To run the live probe, ensure:")
        print()
        print("1. Server is running:")
        print(f"   uv run minerva serve")
        print()
        print("2. Database is accessible:")
        print(f"   export DATABASE_URL='postgresql://...'")
        print()
        print("3. Run the probe:")
        print(f"   uv run python src/scripts/zeroclaw_webhook_e2e.py --run")
        print()
        print("Optional flags:")
        print(f"   --base-url URL    # Default: {DEFAULT_BASE_URL}")
        print(f"   --workspace-id ID # Default: {DEFAULT_WORKSPACE_ID}")
        print(f"   --timeout SECONDS # Default: {DEFAULT_TIMEOUT_SECONDS}")
        print(f"   --json            # Output machine-readable JSON")
        return True


async def main_async() -> int:
    """Async main entry point."""
    parser = argparse.ArgumentParser(
        prog="zeroclaw_webhook_e2e",
        description="E2E probe for Zeroclaw multi-user -> multi-sandbox validation",
        epilog="""
Environment Variables:
    DATABASE_URL        PostgreSQL connection string (required for --run)

Examples:
    # Dry run (validate prerequisites)
    uv run python %(prog)s --dry-run

    # Live execution with defaults
    uv run python %(prog)s --run

    # Live execution with custom endpoint
    uv run python %(prog)s --run --base-url http://localhost:8080

    # JSON output for CI integration
    uv run python %(prog)s --run --json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Validate prerequisites without executing (default)",
    )

    parser.add_argument(
        "--run",
        action="store_true",
        dest="run_live",
        help="Execute live probe against running server",
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of Minerva API (default: {DEFAULT_BASE_URL})",
    )

    parser.add_argument(
        "--workspace-id",
        default=DEFAULT_WORKSPACE_ID,
        help=f"Workspace ID for routing (default: {DEFAULT_WORKSPACE_ID})",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-readable text",
    )

    args = parser.parse_args()

    # --run flag overrides --dry-run default
    if args.run_live:
        args.dry_run = False

    if args.dry_run:
        # Dry run mode - just validate prerequisites
        success = print_dry_run_info()
        return 0 if success else 1

    # Live execution mode
    # Check required environment variables
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]

    if missing_vars:
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "errors": [
                            f"Missing required environment variables: {', '.join(missing_vars)}"
                        ],
                    }
                )
            )
        else:
            print(
                f"Error: Missing required environment variables: {', '.join(missing_vars)}",
                file=sys.stderr,
            )
            print("Set them with:", file=sys.stderr)
            for var in missing_vars:
                print(f"  export {var}=...", file=sys.stderr)
        return 2

    # Run the probe
    async with ZeroclawWebhookE2EProbe(
        base_url=args.base_url,
        workspace_id=args.workspace_id,
        timeout_seconds=args.timeout,
    ) as probe:
        result = await probe.run_probe()

    # Output results
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=" * 60)
        print("Zeroclaw Webhook E2E Probe Results")
        print("=" * 60)
        print(f"Duration: {result.duration_seconds:.2f}s")
        print()
        print("Test Users:")
        for i, uid in enumerate(result.user_ids):
            print(f"  {i + 1}. {uid}")
        print()
        print("Sandboxes Created:")
        if result.sandbox_ids:
            for i, (sid, pref) in enumerate(
                zip(result.sandbox_ids, result.provider_refs)
            ):
                print(f"  {i + 1}. ID: {sid}")
                print(f"     Provider Ref: {pref}")
        else:
            print("  (none found)")
        print()

        if result.success:
            print("✓ PROBE PASSED")
            print("  Multi-user -> multi-sandbox behavior validated!")
            print(f"  Provider refs are unique: {result.provider_refs}")
        else:
            print("✗ PROBE FAILED")
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")

    return 0 if result.success else 1


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
