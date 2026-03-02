"""Minerva CLI main entrypoint with argparse subcommand dispatch."""

import argparse
import sys

from src.cli.commands import init, migrate, serve, scaffold, register, snapshot_build


def main() -> int:
    """Main CLI entrypoint for minerva."""
    parser = argparse.ArgumentParser(
        prog="minerva",
        description="Minerva OSS agent server CLI - manage agent packs, sandboxes, and runtime",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Register subcommands
    init.register_parser(subparsers)
    migrate.register_parser(subparsers)
    serve.register_parser(subparsers)
    scaffold.register_parser(subparsers)
    register.register_parser(subparsers)
    snapshot_build.register_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Dispatch to command handler
    handlers = {
        "init": init.handle,
        "migrate": migrate.handle,
        "serve": serve.handle,
        "scaffold": scaffold.handle,
        "register": register.handle,
        "snapshot": snapshot_build.handle,  # 'snapshot' is the subparser name, 'build' is a positional
    }

    handler = handlers.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
