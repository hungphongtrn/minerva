"""minerva snapshot build - Build the Picoclaw Daytona snapshot."""

import argparse
import asyncio
import sys

from src.services.daytona_snapshot_build_service import DaytonaSnapshotBuildService


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the snapshot build subcommand parser."""
    parser = subparsers.add_parser(
        "snapshot",
        help="Snapshot management commands",
        description="Manage Daytona snapshots for Picoclaw runtime",
    )
    snapshot_subparsers = parser.add_subparsers(
        dest="snapshot_command",
        help="Snapshot commands",
    )

    # snapshot build subcommand
    build_parser = snapshot_subparsers.add_parser(
        "build",
        help="Build the Picoclaw Daytona snapshot",
        description="Build a Daytona snapshot with the Picoclaw runtime image from a Git repository",
    )
    build_parser.add_argument(
        "--repo-url",
        help="Picoclaw Git repository URL (default: from PICOCLAW_REPO_URL env var)",
    )
    build_parser.add_argument(
        "--ref",
        help="Git ref (branch/tag/sha, default: from PICOCLAW_REPO_REF env var or 'main')",
    )
    build_parser.add_argument(
        "--name",
        help="Snapshot name (default: from DAYTONA_PICOCLAW_SNAPSHOT_NAME env var)",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the snapshot command."""
    if args.snapshot_command == "build":
        return _handle_build(args)
    print("Usage: minerva snapshot build", file=sys.stderr)
    return 1


def _handle_build(args: argparse.Namespace) -> int:
    """Handle the snapshot build command."""
    # Create service with CLI args (overriding env vars if provided)
    service = DaytonaSnapshotBuildService(
        repo_url=args.repo_url,
        repo_ref=args.ref,
        snapshot_name=args.name,
    )

    # Log callback to stream build output
    def log_handler(chunk: str) -> None:
        print(chunk, end="", flush=True)

    # Run async build in sync context
    result = asyncio.run(service.build_snapshot(on_logs=log_handler))

    # Exit with appropriate code
    if result.success:
        return 0
    else:
        if result.error_message:
            print(f"\nError: {result.error_message}", file=sys.stderr)
        if result.remediation:
            print(f"Remediation: {result.remediation}", file=sys.stderr)
        return 1
