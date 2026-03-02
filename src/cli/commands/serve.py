"""minerva serve - Start the agent server."""

import argparse
import sys

import uvicorn


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
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks (development only)",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the serve command.

    Gates (cannot be skipped unless --skip-preflight):
    1. DB schema must be at Alembic head (fail with "run `minerva migrate`")
    2. Daytona snapshot must exist (fail with "run `minerva snapshot build`")

    Does NOT auto-migrate.
    """
    if not args.skip_preflight:
        # Run preflight gates
        from src.services.preflight_service import (
            PreflightService,
            format_checklist,
            CheckStatus,
        )

        service = PreflightService()

        # Gate 1: DB schema must be current
        print("Checking database schema...")
        schema_check = service.check_database_schema_current()
        if schema_check.status == CheckStatus.FAIL:
            print(f"\n❌ {schema_check.message}")
            print(f"   → {schema_check.remediation}")
            return 1
        print(f"✅ {schema_check.message}")

        # Gate 2: Picoclaw snapshot must exist (if configured)
        snapshot_name = service._get_picoclaw_snapshot_name()
        if snapshot_name:
            print(f"Checking Picoclaw snapshot '{snapshot_name}'...")
            snapshot_check = service.check_picoclaw_snapshot_exists()
            if snapshot_check.status == CheckStatus.FAIL:
                print(f"\n❌ {snapshot_check.message}")
                print(f"   → {snapshot_check.remediation}")
                return 1
            print(f"✅ {snapshot_check.message}")
        else:
            print("ℹ️  No Picoclaw snapshot configured (DAYTONA_PICOCLAW_SNAPSHOT_NAME)")

        print("\n✅ Preflight checks passed\n")

    # Start server
    print(f"Starting Minerva server on {args.host}:{args.port}")

    uvicorn.run(
        "src.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

    return 0
