"""Pseudo-toy CLI for exploring Zeroclaw gateway and Minerva OSS /runs SSE flow.

A single-file CLI for probing:
- Minerva OSS /runs endpoint with SSE streaming
- Direct Zeroclaw gateway health and execute endpoints

No external credentials required for dry-run mode.
"""

import argparse
import json
import sys
import uuid
from typing import Optional

import httpx


def load_zeroclaw_spec(path: str = "src/integrations/zeroclaw/spec.json") -> dict:
    """Load Zeroclaw spec from JSON file."""
    import json as json_lib
    from pathlib import Path

    spec_path = Path(path)
    if not spec_path.exists():
        raise FileNotFoundError(f"Zeroclaw spec not found: {path}")

    with open(spec_path, "r", encoding="utf-8") as f:
        return json_lib.load(f)


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Dry-run mode: show spec values and example commands without requiring DB/credentials."""
    try:
        spec = load_zeroclaw_spec()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Ensure you run from the repo root directory.", file=sys.stderr)
        return 1

    gateway = spec.get("gateway", {})
    auth = spec.get("auth", {})

    print("=" * 60)
    print("ZEROCALW SPEC DETECTED")
    print("=" * 60)
    print(f"  health_path:     {gateway.get('health_path', '/health')}")
    print(f"  execute_path:    {gateway.get('execute_path', '/webhook')}")
    print(f"  auth.mode:       {auth.get('mode', 'none')}")
    print(f"  gateway.port:    {gateway.get('port', 18790)}")
    print()

    print("=" * 60)
    print("EXAMPLE COMMANDS")
    print("=" * 60)
    print()
    print("1) Probe OSS /runs endpoint (requires Minerva server running):")
    print(
        "   uv run python src/scripts/pseudo_toy.py runs "
        "--minerva-url http://127.0.0.1:8000 --user-id toy-user"
    )
    print()
    print("2) Call sandbox gateway directly (requires running sandbox):")
    print(
        "   uv run python src/scripts/pseudo_toy.py gateway "
        '--sandbox-url http://localhost:18790 --message "Hello!"'
    )
    print()

    print("=" * 60)
    print("COMMON ENVIRONMENT VARIABLES")
    print("=" * 60)
    print("  DATABASE_URL           - PostgreSQL connection URL")
    print("  MINERVA_WORKSPACE_ID   - Developer workspace UUID for OSS mode")
    print("  SANDBOX_PROFILE        - 'local_compose' or 'daytona'")
    print("  DAYTONA_API_KEY        - Required for Daytona sandbox provisioning")
    print("  DAYTONA_TARGET         - Target region (default: 'us')")
    print("  ZER0CLAW_GATEWAY_TOKEN - Bearer token for gateway auth")
    print()

    print("=" * 60)
    print("FILES REFERENCED")
    print("=" * 60)
    print("  src/integrations/zeroclaw/spec.json    - Gateway contract spec")
    print("  src/config/settings.py                 - Environment variable defs")
    print("  .env.example                           - Example configuration")
    print()

    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    """Exercise Minerva -> sandbox -> gateway flow via OSS POST /runs SSE."""
    minerva_url = args.minerva_url.rstrip("/")
    user_id = args.user_id
    session_ids = args.session_ids
    messages = args.messages
    timeout_seconds = args.timeout_seconds

    if len(session_ids) != len(messages):
        print(
            f"ERROR: session_ids ({len(session_ids)}) must match messages ({len(messages)})",
            file=sys.stderr,
        )
        return 1

    # Track sandbox info from SSE events
    sandbox_info = {}
    exit_code = 0

    for idx, (session_id, message) in enumerate(zip(session_ids, messages)):
        run_id = str(uuid.uuid4())
        idempotency_key = f"pseudo-toy-{uuid.uuid4()}"

        print(f"\n{'=' * 60}")
        print(f"RUN {idx + 1}/{len(session_ids)}")
        print(f"{'=' * 60}")
        print(f"  Session ID:       {session_id}")
        print(f"  Message:          {message}")
        print(f"  Run ID:           {run_id}")
        print(f"  Idempotency Key:  {idempotency_key}")
        print()

        url = f"{minerva_url}/runs"
        headers = {
            "X-User-ID": user_id,
            "X-Session-ID": session_id,
            "X-Idempotency-Key": idempotency_key,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        payload = {"message": message}

        print(f"POST {url}")
        print(f"Headers: {json.dumps(headers, indent=2)}")
        print(f"Body: {json.dumps(payload, indent=2)}")
        print()

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code != 200:
                        print(f"ERROR: HTTP {response.status_code}", file=sys.stderr)
                        try:
                            error_body = response.read().decode("utf-8")
                            print(f"Response: {error_body}", file=sys.stderr)
                        except Exception:
                            pass
                        exit_code = 1
                        continue

                    print("SSE EVENT TIMELINE:")
                    print("-" * 40)

                    for line in response.iter_lines():
                        if not line:
                            continue

                        line_str = (
                            line.decode("utf-8") if isinstance(line, bytes) else line
                        )

                        if line_str.startswith("data: "):
                            data = line_str[6:]  # Remove "data: " prefix
                            try:
                                event_data = json.loads(data)
                                event_type = event_data.get("type", "unknown")
                                print(f"  [{event_type}]")

                                # Print key fields based on event type
                                if event_type == "queued":
                                    print(f"    position: {event_data.get('position')}")
                                elif event_type == "provisioning":
                                    print(f"    step: {event_data.get('step')}")
                                    print(f"    message: {event_data.get('message')}")
                                elif event_type == "running":
                                    print(f"    step: {event_data.get('step')}")
                                elif event_type == "message":
                                    print(f"    role: {event_data.get('role')}")
                                    content = event_data.get("content", "")
                                    if len(content) > 100:
                                        content = content[:97] + "..."
                                    print(f"    content: {content}")
                                elif event_type == "completed":
                                    print("    status: completed")
                                elif event_type == "failed":
                                    print(f"    error: {event_data.get('error')}")
                                    print(
                                        f"    category: {event_data.get('error_category')}"
                                    )
                                    exit_code = 1

                                # Track sandbox info from events
                                if "sandbox_id" in event_data:
                                    sandbox_info["sandbox_id"] = event_data[
                                        "sandbox_id"
                                    ]
                                if "gateway_url" in event_data:
                                    sandbox_info["gateway_url"] = event_data[
                                        "gateway_url"
                                    ]

                                # Stop on terminal events
                                if event_type in ("completed", "failed"):
                                    break

                            except json.JSONDecodeError:
                                print(f"  [raw] {data}")

        except httpx.TimeoutException:
            print(f"ERROR: Request timed out after {timeout_seconds}s", file=sys.stderr)
            exit_code = 1
        except httpx.RequestError as e:
            print(f"ERROR: Request failed: {e}", file=sys.stderr)
            exit_code = 1

    print()

    # DB check if requested
    if args.db_check:
        print("=" * 60)
        print("DATABASE CHECK")
        print("=" * 60)

        try:
            from src.db.session import get_session_factory
            from src.db.repositories.sandbox_instance_repository import (
                SandboxInstanceRepository,
            )
            from src.config.settings import settings
            from uuid import UUID

            # Get workspace ID from settings or override
            workspace_id_str = args.workspace_id or settings.MINERVA_WORKSPACE_ID
            if not workspace_id_str or workspace_id_str == "auto":
                print(
                    "ERROR: MINERVA_WORKSPACE_ID not set. Use --workspace-id or set in .env",
                    file=sys.stderr,
                )
                return 1

            workspace_id = UUID(workspace_id_str)

            Session = get_session_factory()
            with Session() as db:
                repo = SandboxInstanceRepository(db)
                sandboxes = repo.list_by_workspace(
                    workspace_id=workspace_id,
                    include_inactive=True,
                    external_user_id=user_id,
                )

                print(f"Found {len(sandboxes)} sandbox(es) for user '{user_id}'")

                if len(sandboxes) == 1:
                    sandbox = sandboxes[0]
                    print(f"  provider_ref: {sandbox.provider_ref}")
                    print(f"  gateway_url:  {sandbox.gateway_url}")
                    print(f"  state:        {sandbox.state.value}")
                    print()
                    print(
                        "ASSERTION PASSED: Exactly 1 sandbox for user (single-sandbox mode)"
                    )
                elif len(sandboxes) == 0:
                    print("WARNING: No sandboxes found for user", file=sys.stderr)
                    exit_code = 1
                else:
                    print(
                        f"WARNING: Found {len(sandboxes)} sandboxes (expected 1)",
                        file=sys.stderr,
                    )
                    exit_code = 1

        except ImportError as e:
            print(f"ERROR: Cannot import DB modules: {e}", file=sys.stderr)
            print(
                "Ensure you run from repo root with proper Python path",
                file=sys.stderr,
            )
            return 1
        except Exception as e:
            print(f"ERROR: DB check failed: {e}", file=sys.stderr)
            return 1

    return exit_code


def cmd_gateway(args: argparse.Namespace) -> int:
    """Call sandbox gateway endpoints directly (health + execute)."""
    sandbox_url = args.sandbox_url.rstrip("/")
    message = args.message
    sender_id = args.sender_id
    session_id = args.session_id
    token = args.token
    timeout_seconds = args.timeout_seconds

    try:
        spec = load_zeroclaw_spec()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    gateway_spec = spec.get("gateway", {})
    auth_spec = spec.get("auth", {})
    examples = spec.get("examples", {})

    health_path = gateway_spec.get("health_path", "/health")
    execute_path = gateway_spec.get("execute_path", "/webhook")
    auth_mode = auth_spec.get("mode", "none")

    # Build URLs
    health_url = f"{sandbox_url}{health_path}"
    execute_url = f"{sandbox_url}{execute_path}"
    alternate_execute_url = f"{sandbox_url}/execute"
    if execute_path == "/execute":
        alternate_execute_url = f"{sandbox_url}/webhook"

    print("=" * 60)
    print("GATEWAY DIRECT CALL")
    print("=" * 60)
    print(f"  Sandbox URL:      {sandbox_url}")
    print(f"  Auth Mode:        {auth_mode}")
    print(f"  Health Path:      {health_path}")
    print(f"  Execute Path:     {execute_path}")
    print()

    # Step 1: Health check
    print(f"STEP 1: Health Check")
    print(f"  GET {health_url}")

    headers = {"Content-Type": "application/json"}
    if auth_mode == "bearer" and token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(health_url, headers=headers)
            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  Response: {json.dumps(data, indent=2)}")
                except Exception:
                    print(f"  Response: {response.text}")
            else:
                print(
                    f"  ERROR: Health check failed with status {response.status_code}"
                )
                print(f"  Response: {response.text}")
                return 1

    except httpx.TimeoutException:
        print(
            f"  ERROR: Health check timed out after {timeout_seconds}s", file=sys.stderr
        )
        return 1
    except httpx.RequestError as e:
        print(f"  ERROR: Health check failed: {e}", file=sys.stderr)
        return 1

    print()

    # Step 2: Execute request
    print(f"STEP 2: Execute Request")

    # Build payload from spec example
    execute_request_example = examples.get("execute_request", {})
    payload = {
        "message": message,
        "context": {
            "session_id": session_id,
            "sender_id": sender_id,
            **execute_request_example.get("context", {}),
        },
    }

    # Remove example-specific fields that we override
    payload["context"].pop("session_id", None)
    payload["context"].pop("sender_id", None)
    payload["context"]["session_id"] = session_id
    payload["context"]["sender_id"] = sender_id

    print(f"  POST {execute_url}")
    print(f"  Headers: {json.dumps(headers, indent=2)}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(execute_url, headers=headers, json=payload)

            # Retry with alternate path if 404
            if response.status_code == 404:
                print(
                    f"  Primary path returned 404, trying alternate: {alternate_execute_url}"
                )
                response = client.post(
                    alternate_execute_url, headers=headers, json=payload
                )

            print(f"  Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  Response: {json.dumps(data, indent=2)}")
                except Exception:
                    print(f"  Response (raw): {response.text}")
            else:
                print(f"  ERROR: Execute failed with status {response.status_code}")
                try:
                    data = response.json()
                    print(f"  Response: {json.dumps(data, indent=2)}")
                except Exception:
                    print(f"  Response: {response.text}")
                return 1

    except httpx.TimeoutException:
        print(f"  ERROR: Execute timed out after {timeout_seconds}s", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"  ERROR: Execute failed: {e}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("CURL EQUIVALENT (auth redacted)")
    print("=" * 60)

    # Generate curl command with redacted auth
    curl_headers = []
    for k, v in headers.items():
        if k.lower() == "authorization":
            curl_headers.append(f"-H '{k}: Bearer <REDACTED>'")
        else:
            curl_headers.append(f"-H '{k}: {v}'")

    curl_cmd = (
        f"curl -X POST '{execute_url}' \\\n"
        + " \\\n".join(f"  {h}" for h in curl_headers)
        + f" \\\n  -d '{json.dumps(payload)}'"
    )
    print(curl_cmd)

    return 0


def main():
    """Main entry point for pseudo_toy CLI."""
    parser = argparse.ArgumentParser(
        prog="pseudo_toy",
        description="CLI for exploring Zeroclaw gateway and Minerva OSS /runs SSE flow",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # dry-run command
    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Show spec values and example commands (no credentials needed)",
    )
    dry_run_parser.set_defaults(func=cmd_dry_run)

    # runs command
    runs_parser = subparsers.add_parser(
        "runs",
        help="Exercise Minerva -> sandbox -> gateway flow via OSS /runs SSE",
    )
    runs_parser.add_argument(
        "--minerva-url",
        default="http://127.0.0.1:8000",
        help="Minerva server URL (default: http://127.0.0.1:8000)",
    )
    runs_parser.add_argument(
        "--user-id",
        required=True,
        help="User ID (maps to X-User-ID header)",
    )
    runs_parser.add_argument(
        "--session-ids",
        nargs=2,
        default=["s1", "s2"],
        help="Two session IDs (default: s1 s2)",
    )
    runs_parser.add_argument(
        "--messages",
        nargs=2,
        default=["hello-1", "hello-2"],
        help="Two messages (default: 'hello-1' 'hello-2')",
    )
    runs_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Request timeout in seconds (default: 60)",
    )
    runs_parser.add_argument(
        "--db-check",
        action="store_true",
        help="Enable DB check after runs (requires DATABASE_URL configured)",
    )
    runs_parser.add_argument(
        "--workspace-id",
        default=None,
        help="Override workspace ID for DB check",
    )
    runs_parser.set_defaults(func=cmd_runs)

    # gateway command
    gateway_parser = subparsers.add_parser(
        "gateway",
        help="Call sandbox gateway directly (health + execute)",
    )
    gateway_parser.add_argument(
        "--sandbox-url",
        required=True,
        help="Base URL of the sandbox gateway",
    )
    gateway_parser.add_argument(
        "--message",
        default="Hello, Zeroclaw!",
        help="Message to send (default: 'Hello, Zeroclaw!')",
    )
    gateway_parser.add_argument(
        "--sender-id",
        default="user-456",
        help="Sender ID for context (default: user-456)",
    )
    gateway_parser.add_argument(
        "--session-id",
        default="session-123",
        help="Session ID for context (default: session-123)",
    )
    gateway_parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for authentication (if auth mode is bearer)",
    )
    gateway_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    gateway_parser.set_defaults(func=cmd_gateway)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
