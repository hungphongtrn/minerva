"""minerva serve - Start the agent server."""

import argparse
import sys


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the serve subcommand parser."""
    parser = subparsers.add_parser(
        "serve",
        help="Start the agent server",
        description="Start the Minerva agent server with preflight validation",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the serve command."""
    # Implementation in task 2
    print("minerva serve: Not yet implemented")
    return 0
