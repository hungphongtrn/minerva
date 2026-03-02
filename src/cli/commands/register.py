"""minerva register - Register an agent pack with the system."""

import argparse
import sys


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the register subcommand parser."""
    parser = subparsers.add_parser(
        "register",
        help="Register an agent pack",
        description="Register an agent pack from a local directory path",
    )
    parser.add_argument(
        "path",
        help="Path to agent pack directory",
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Workspace UUID to associate with the pack",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the register command."""
    # Implementation in future plan
    print("minerva register: Not yet implemented")
    return 0
