"""minerva snapshot build - Build the Picoclaw Daytona snapshot."""

import argparse
import sys


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
        description="Build a Daytona snapshot with the Picoclaw runtime image",
    )
    build_parser.add_argument(
        "--name",
        help="Snapshot name (default: from DAYTONA_PICOCLAW_SNAPSHOT_NAME env var)",
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing snapshot if it exists",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the snapshot command."""
    if args.snapshot_command == "build":
        return _handle_build(args)
    print("Usage: minerva snapshot build", file=sys.stderr)
    return 1


def _handle_build(args: argparse.Namespace) -> int:
    """Handle the snapshot build command."""
    # Implementation in future plan
    print("minerva snapshot build: Not yet implemented")
    return 0
