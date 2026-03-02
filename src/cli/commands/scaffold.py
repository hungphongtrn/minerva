"""minerva scaffold - Generate a starter agent pack."""

import argparse
import sys


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the scaffold subcommand parser."""
    parser = subparsers.add_parser(
        "scaffold",
        help="Generate a starter agent pack",
        description="Create a minimal agent pack with AGENT.md, SOUL.md, IDENTITY.md, and skills/",
    )
    parser.add_argument(
        "--out",
        default="./agent-pack",
        help="Output directory for generated pack (default: ./agent-pack)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in output directory",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the scaffold command."""
    # Implementation in task 3
    print("minerva scaffold: Not yet implemented")
    return 0
