#!/usr/bin/env python3
"""Standalone Daytona SDK playground for ZeroClaw sandboxes.

This script is intentionally independent from Minerva's runtime services.
It demonstrates how to:

1. Create or attach to a Daytona sandbox.
2. Upload a local ZeroClaw source tree.
3. Execute commands inside the sandbox.
4. Optionally start the ZeroClaw gateway and call /health.
5. Optionally open an interactive command REPL.

Usage examples:

    # Create a sandbox, upload local ZeroClaw repo, run demo commands, cleanup
    uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py

    # Keep sandbox alive for manual exploration
    uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py --keep-sandbox

    # Attach to existing sandbox and run a command
    uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py \
      --sandbox-id <sandbox-id> --command "ls -la /workspace/zeroclaw"

    # Start gateway and check /health
    uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py --start-gateway

    # Delete a sandbox created earlier
    uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py \
      --sandbox-id <sandbox-id> --cleanup
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from daytona import (
    AsyncDaytona,
    CreateSandboxFromSnapshotParams,
    CreateSandboxFromImageParams,
    DaytonaConfig,
    DaytonaError,
)

DEFAULT_REPO_PATH = "/Users/phong/Workspace/minerva/reference_repos/zeroclaw"
DEFAULT_SNAPSHOT_NAME = "picoclaw-snapshot"
DEFAULT_TARGET = "us"
DEFAULT_GATEWAY_PORT = 3000

SKIP_DIR_NAMES = {
    ".git",
    "target",
    ".idea",
    ".vscode",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


@dataclass
class ExecResult:
    """Result of a command executed in a Daytona sandbox."""

    command: str
    exit_code: int
    output: str


def _default_repo_path() -> str:
    """Return the most likely local ZeroClaw path."""
    configured = Path(DEFAULT_REPO_PATH)
    if configured.exists():
        return str(configured)

    fallback = Path("reference_repos/zeroclaw")
    return str(fallback)


def _normalize_preview_url(preview: Any) -> str | None:
    """Extract preview URL from SDK response shape."""
    if isinstance(preview, str) and preview.startswith("http"):
        return preview.rstrip("/")

    for attr in ("url", "preview_url", "link"):
        value = getattr(preview, attr, None)
        if isinstance(value, str) and value.startswith("http"):
            return value.rstrip("/")

    if isinstance(preview, dict):
        for key in ("url", "preview_url", "link"):
            value = preview.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value.rstrip("/")

    model_dump = getattr(preview, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        if isinstance(data, dict):
            for key in ("url", "preview_url", "link"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value.rstrip("/")

    return None


class DaytonaZeroclawPlayground:
    """Independent Daytona SDK workflow for ZeroClaw exploration."""

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        target: str,
        snapshot_name: str,
        gateway_port: int,
    ):
        self._api_key = api_key
        self._api_url = api_url
        self._target = target
        self._snapshot_name = snapshot_name
        self._gateway_port = gateway_port

    def _create_config(self) -> DaytonaConfig:
        kwargs: dict[str, Any] = {"target": self._target}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_url:
            kwargs["api_url"] = self._api_url
        return DaytonaConfig(**kwargs)

    async def _exec(
        self,
        sandbox: Any,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> ExecResult:
        response = await sandbox.process.exec(command, cwd=cwd, timeout=timeout)
        exit_code = int(getattr(response, "exit_code", 1))
        output = str(getattr(response, "result", "") or "")
        return ExecResult(command=command, exit_code=exit_code, output=output)

    async def create_sandbox(self, daytona: AsyncDaytona, name: str | None = None) -> Any:
        """Create sandbox, trying snapshot first, falling back to base image."""
        try:
            params = CreateSandboxFromSnapshotParams(
                name=name,
                snapshot=self._snapshot_name,
                labels={
                    "purpose": "zeroclaw-playground",
                    "source": "independent-script",
                },
            )
            return await daytona.create(params, timeout=120)
        except DaytonaError as e:
            error_str = str(e).lower()
            if "not found" in error_str or "snapshot" in error_str:
                print(f"Snapshot '{self._snapshot_name}' not found. Using base image instead...")
                # Use a standard Debian-based image that can run Rust
                params = CreateSandboxFromImageParams(
                    name=name,
                    image="debian:trixie-slim",
                    labels={
                        "purpose": "zeroclaw-playground",
                        "source": "independent-script",
                    },
                )
                return await daytona.create(params, timeout=120)
            raise

    async def delete_sandbox(self, daytona: AsyncDaytona, sandbox_id: str) -> None:
        sandbox = await daytona.get(sandbox_id)
        await daytona.delete(sandbox, timeout=120)

    def build_repo_archive(self, repo_path: Path) -> bytes:
        """Create gzipped tarball of local ZeroClaw repo for upload."""
        if not repo_path.exists() or not repo_path.is_dir():
            raise FileNotFoundError(f"ZeroClaw repo path not found: {repo_path}")

        buffer = io.BytesIO()

        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]

                root_path = Path(root)
                for file_name in sorted(files):
                    file_path = root_path / file_name

                    if file_path.name.endswith(".pyc"):
                        continue

                    rel_path = file_path.relative_to(repo_path)
                    tar.add(file_path, arcname=str(rel_path), recursive=False)

        return buffer.getvalue()

    async def upload_repo(self, sandbox: Any, repo_path: Path, remote_path: str) -> None:
        archive = self.build_repo_archive(repo_path)
        archive_path = "/tmp/zeroclaw.tar.gz"

        await sandbox.fs.upload_file(archive, archive_path, timeout=1800)

        extract_cmd = (
            f"mkdir -p {remote_path} && "
            f"tar -xzf {archive_path} -C {remote_path} && "
            f"rm -f {archive_path}"
        )
        result = await self._exec(sandbox, extract_cmd, timeout=300)
        if result.exit_code != 0:
            raise RuntimeError(
                "Failed to extract uploaded repo archive in sandbox:\n"
                f"command={result.command}\n"
                f"output={result.output}"
            )

    async def setup_rust_toolchain(self, sandbox: Any) -> ExecResult:
        """Install Rust toolchain and build dependencies in sandbox."""
        print("Installing build dependencies...")
        deps_result = await self._exec(
            sandbox,
            "apt-get update && apt-get install -y build-essential pkg-config ca-certificates curl git",
            timeout=300,
        )
        if deps_result.exit_code != 0:
            raise RuntimeError(f"Failed to install build dependencies: {deps_result.output}")

        print("Installing Rust toolchain...")
        rustup_cmd = (
            "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
            "sh -s -- -y --default-toolchain stable"
        )
        rustup_result = await self._exec(sandbox, rustup_cmd, timeout=300)
        if rustup_result.exit_code != 0:
            raise RuntimeError(f"Failed to install Rust: {rustup_result.output}")

        print("Setting up environment...")
        # Use full path to cargo for verification
        cargo_bin = "$HOME/.cargo/bin"
        env_result = await self._exec(
            sandbox,
            f"{cargo_bin}/rustc --version && {cargo_bin}/cargo --version",
            timeout=30,
        )
        if env_result.exit_code != 0:
            raise RuntimeError(f"Failed to setup Rust environment: {env_result.output}")

        # Create a cargo env file manually if it doesn't exist
        await self._exec(
            sandbox,
            f"mkdir -p $HOME/.cargo && echo 'export PATH=\"{cargo_bin}:$PATH\"' > $HOME/.cargo/env",
            timeout=10,
        )

        return env_result

    async def build_zeroclaw(self, sandbox: Any, repo_path: str) -> ExecResult:
        """Build Zeroclaw from source in the sandbox."""
        print(f"Building Zeroclaw from {repo_path}...")
        build_cmd = f". $HOME/.cargo/env && cd {repo_path} && cargo build --release --locked"
        return await self._exec(sandbox, build_cmd, timeout=600)

    async def install_zeroclaw(self, sandbox: Any, repo_path: str) -> ExecResult:
        """Install Zeroclaw binary to a location in PATH."""
        print("Installing Zeroclaw binary...")
        install_cmd = (
            f"cp {repo_path}/target/release/zeroclaw /usr/local/bin/zeroclaw && "
            "chmod +x /usr/local/bin/zeroclaw"
        )
        return await self._exec(sandbox, install_cmd, timeout=30)

    async def install_zeroclaw_prebuilt(self, sandbox: Any) -> ExecResult:
        """Install Zeroclaw from prebuilt binary using bootstrap script."""
        print("Installing Zeroclaw from prebuilt binary...")

        # Install curl and tar if needed
        deps_result = await self._exec(
            sandbox,
            "apt-get update && apt-get install -y curl tar ca-certificates",
            timeout=120,
        )
        if deps_result.exit_code != 0:
            raise RuntimeError(f"Failed to install dependencies: {deps_result.output}")

        # Use the bootstrap script to install prebuilt binary
        install_cmd = (
            "curl -fsSL https://raw.githubusercontent.com/openagen/zeroclaw/main/scripts/bootstrap.sh | "
            "bash -s -- --prefer-prebuilt --skip-build"
        )
        return await self._exec(sandbox, install_cmd, timeout=120)

    async def setup_zeroclaw_config(
        self, sandbox: Any, workspace_dir: str = "/workspace"
    ) -> ExecResult:
        """Create a minimal Zeroclaw config for the sandbox."""
        print("Setting up Zeroclaw config...")
        config_dir = f"{workspace_dir}/.zeroclaw"
        config_content = f"""workspace_dir = "{workspace_dir}"
config_path = "{config_dir}/config.toml"
api_key = ""
default_provider = "openrouter"
default_model = "anthropic/claude-sonnet-4-20250514"
default_temperature = 0.7

[gateway]
port = {self._gateway_port}
host = "0.0.0.0"
allow_public_bind = true

[autonomy]
level = "supervised"
workspace_only = true

[runtime]
kind = "native"
"""
        config_cmd = (
            f"mkdir -p {config_dir} && "
            f"cat > {config_dir}/config.toml << 'EOF'\n{config_content}\nEOF"
        )
        return await self._exec(sandbox, config_cmd, timeout=30)

    async def get_preview_url(self, sandbox: Any, port: int) -> str | None:
        preview = await sandbox.get_preview_link(port)
        return _normalize_preview_url(preview)

    async def start_gateway(self, sandbox: Any) -> ExecResult:
        # Try to find zeroclaw binary in various locations
        command = (
            f"ZEROCLAW_BIN=''; "
            f"if [ -x /usr/local/bin/zeroclaw ]; then ZEROCLAW_BIN=/usr/local/bin/zeroclaw; "
            f"elif [ -x $HOME/.cargo/bin/zeroclaw ]; then ZEROCLAW_BIN=$HOME/.cargo/bin/zeroclaw; "
            f"elif command -v zeroclaw >/dev/null 2>&1; then ZEROCLAW_BIN=zeroclaw; "
            f"elif [ -x /workspace/zeroclaw/target/release/zeroclaw ]; then ZEROCLAW_BIN=/workspace/zeroclaw/target/release/zeroclaw; "
            f"fi; "
            f'if [ -n "$ZEROCLAW_BIN" ]; then '
            f"nohup $ZEROCLAW_BIN gateway --host 0.0.0.0 --port {self._gateway_port} "
            f">/tmp/zeroclaw-gateway.log 2>&1 & "
            f'echo "started:$ZEROCLAW_BIN"; '
            f"else echo 'missing:zeroclaw'; exit 127; fi"
        )
        return await self._exec(sandbox, command)

    async def wait_for_gateway_health(
        self,
        preview_url: str,
        *,
        timeout_seconds: int = 45,
    ) -> tuple[bool, str]:
        health_url = f"{preview_url}/health"

        async with httpx.AsyncClient(timeout=5.0) as client:
            start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start) < timeout_seconds:
                try:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        return True, response.text
                except Exception:
                    await asyncio.sleep(1.0)
                    continue

                await asyncio.sleep(1.0)

        return False, "Gateway health check timed out"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daytona_zeroclaw_sandbox_playground",
        description=(
            "Independent Daytona SDK playground to launch and explore a ZeroClaw sandbox"
        ),
    )

    parser.add_argument(
        "--sandbox-id",
        help="Attach to an existing sandbox by ID instead of creating a new one",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the sandbox from --sandbox-id and exit",
    )
    parser.add_argument(
        "--snapshot-name",
        default=os.environ.get("DAYTONA_PICOCLAW_SNAPSHOT_NAME", DEFAULT_SNAPSHOT_NAME),
        help=f"Daytona snapshot to provision from (default: {DEFAULT_SNAPSHOT_NAME})",
    )
    parser.add_argument(
        "--sandbox-name",
        default=f"zeroclaw-playground-{uuid4().hex[:8]}",
        help="Name for a newly created sandbox",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DAYTONA_TARGET", DEFAULT_TARGET),
        help=f"Daytona target region (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("DAYTONA_API_KEY", ""),
        help="Daytona API key (defaults to DAYTONA_API_KEY)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("DAYTONA_API_URL", ""),
        help="Daytona API URL for self-hosted deployments (defaults to DAYTONA_API_URL)",
    )
    parser.add_argument(
        "--repo-path",
        default=_default_repo_path(),
        help="Local ZeroClaw repo path to upload into /workspace/zeroclaw",
    )
    parser.add_argument(
        "--remote-repo-path",
        default="/workspace/zeroclaw",
        help="Remote sandbox path where the repo is extracted",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip uploading local ZeroClaw source tree",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="Command to execute inside sandbox (can be repeated)",
    )
    parser.add_argument(
        "--start-gateway",
        action="store_true",
        help="Attempt to start ZeroClaw gateway and run /health check",
    )
    parser.add_argument(
        "--build-from-source",
        action="store_true",
        dest="build_from_source",
        help="Build Zeroclaw from source in the sandbox (automatic when no snapshot)",
    )
    parser.add_argument(
        "--prebuilt",
        action="store_true",
        help="Use prebuilt Zeroclaw binary instead of building from source",
    )
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=DEFAULT_GATEWAY_PORT,
        help=f"Gateway port for --start-gateway (default: {DEFAULT_GATEWAY_PORT})",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open an interactive command REPL after setup",
    )
    parser.add_argument(
        "--keep-sandbox",
        action="store_true",
        help="Do not delete newly created sandbox on exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary at the end",
    )

    return parser


async def _interactive_repl(playground: DaytonaZeroclawPlayground, sandbox: Any) -> None:
    print("\nInteractive mode. Type commands to run in sandbox. Type 'exit' to quit.")

    while True:
        line = await asyncio.to_thread(input, "sandbox> ")
        command = line.strip()

        if not command:
            continue
        if command.lower() in {"exit", "quit"}:
            break

        result = await playground._exec(sandbox, command, timeout=600)
        print(f"\n$ {result.command}")
        print(f"exit_code={result.exit_code}")
        print(result.output.rstrip() or "(no output)")


async def main_async() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if args.cleanup and not args.sandbox_id:
        print("Error: --cleanup requires --sandbox-id", file=sys.stderr)
        return 2

    playground = DaytonaZeroclawPlayground(
        api_key=args.api_key,
        api_url=args.api_url,
        target=args.target,
        snapshot_name=args.snapshot_name,
        gateway_port=args.gateway_port,
    )

    summary: dict[str, Any] = {
        "created": False,
        "sandbox_id": args.sandbox_id,
        "snapshot": args.snapshot_name,
        "target": args.target,
        "uploaded_repo": False,
        "gateway": None,
        "commands": [],
        "cleaned_up": False,
    }

    config = playground._create_config()
    async with AsyncDaytona(config=config) as daytona:
        if args.cleanup:
            try:
                await playground.delete_sandbox(daytona, args.sandbox_id)
            except DaytonaError as exc:
                print(
                    f"Failed to cleanup sandbox {args.sandbox_id}: {exc}",
                    file=sys.stderr,
                )
                return 1

            print(f"Deleted sandbox: {args.sandbox_id}")
            return 0

        created_here = False

        try:
            if args.sandbox_id:
                sandbox = await daytona.get(args.sandbox_id)
            else:
                sandbox = await playground.create_sandbox(daytona, args.sandbox_name)
                created_here = True

            sandbox_id = getattr(sandbox, "id", args.sandbox_id or "unknown")
            summary["created"] = created_here
            summary["sandbox_id"] = sandbox_id

            print(f"Sandbox ready: {sandbox_id}")

            if not args.skip_upload:
                repo_path = Path(args.repo_path).expanduser().resolve()
                print(f"Uploading local repo: {repo_path}")
                await playground.upload_repo(sandbox, repo_path, args.remote_repo_path)
                summary["uploaded_repo"] = True
                print(f"Uploaded to: {args.remote_repo_path}")

            bootstrap_commands = [
                "pwd",
                "ls -la /workspace",
                f"ls -la {args.remote_repo_path}" if not args.skip_upload else "ls -la /workspace",
            ]

            for command in bootstrap_commands + list(args.command):
                result = await playground._exec(sandbox, command, timeout=300)
                summary["commands"].append(asdict(result))
                print(f"\n$ {result.command}")
                print(f"exit_code={result.exit_code}")
                print(result.output.rstrip() or "(no output)")

            if args.start_gateway:
                # If using base image (no snapshot) or explicitly requested, we need to build from source
                if not args.sandbox_id and (
                    args.build_from_source or args.snapshot_name == DEFAULT_SNAPSHOT_NAME
                ):
                    if args.prebuilt:
                        print("\nInstalling Zeroclaw from prebuilt binary...")
                        install_result = await playground.install_zeroclaw_prebuilt(sandbox)
                        if install_result.exit_code != 0:
                            print("Prebuilt install failed, falling back to source build...")
                            args.prebuilt = False

                    if not args.prebuilt:
                        print("\nBuilding Zeroclaw from source (no snapshot available)...")
                        await playground.setup_rust_toolchain(sandbox)
                        build_result = await playground.build_zeroclaw(
                            sandbox, args.remote_repo_path
                        )
                        if build_result.exit_code != 0:
                            raise RuntimeError(f"Failed to build Zeroclaw: {build_result.output}")
                        print("Build successful!")

                        install_result = await playground.install_zeroclaw(
                            sandbox, args.remote_repo_path
                        )
                        if install_result.exit_code != 0:
                            raise RuntimeError(
                                f"Failed to install Zeroclaw: {install_result.output}"
                            )

                    print("Installed to /usr/local/bin/zeroclaw")

                    config_result = await playground.setup_zeroclaw_config(sandbox, "/workspace")
                    if config_result.exit_code != 0:
                        raise RuntimeError(f"Failed to setup config: {config_result.output}")
                    print("Config created at /workspace/.zeroclaw/config.toml")

                start_result = await playground.start_gateway(sandbox)
                gateway_summary: dict[str, Any] = {
                    "start_command_exit_code": start_result.exit_code,
                    "start_command_output": start_result.output,
                    "preview_url": None,
                    "health_ok": False,
                    "health_response": None,
                }

                preview_url = await playground.get_preview_url(sandbox, args.gateway_port)
                if preview_url:
                    gateway_summary["preview_url"] = preview_url
                    ok, health_response = await playground.wait_for_gateway_health(preview_url)
                    gateway_summary["health_ok"] = ok
                    gateway_summary["health_response"] = health_response

                    print("\nGateway interaction")
                    print(f"preview_url={preview_url}")
                    print(f"health_ok={ok}")
                    print("curl example:")
                    print(f"  curl -sS {preview_url}/health")
                    print(
                        "  curl -sS -X POST "
                        f"{preview_url}/webhook "
                        "-H 'Authorization: Bearer <token-if-required>' "
                        "-H 'Content-Type: application/json' "
                        '-d \'{"message":"Hello from Daytona"}\''
                    )
                else:
                    print("\nGateway preview URL could not be resolved.")

                summary["gateway"] = gateway_summary

            if args.interactive:
                await _interactive_repl(playground, sandbox)

        except (DaytonaError, FileNotFoundError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            if args.json:
                print(json.dumps(summary, indent=2))
            return 1
        finally:
            should_cleanup = created_here and not args.keep_sandbox and not args.interactive
            if should_cleanup and summary.get("sandbox_id"):
                try:
                    sandbox = await daytona.get(summary["sandbox_id"])
                    await daytona.delete(sandbox, timeout=120)
                    summary["cleaned_up"] = True
                    print(f"\nCleaned up sandbox: {summary['sandbox_id']}")
                except DaytonaError as cleanup_error:
                    print(
                        f"Warning: failed to cleanup sandbox {summary['sandbox_id']}: {cleanup_error}",
                        file=sys.stderr,
                    )

    if args.keep_sandbox and summary.get("sandbox_id"):
        print("\nSandbox kept for exploration.")
        print("Reuse it with:")
        print(
            "  uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py "
            f"--sandbox-id {summary['sandbox_id']} --interactive"
        )
        print("Delete it with:")
        print(
            "  uv run python src/scripts/daytona_zeroclaw_sandbox_playground.py "
            f"--sandbox-id {summary['sandbox_id']} --cleanup"
        )

    if args.json:
        print(json.dumps(summary, indent=2))

    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nCancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
