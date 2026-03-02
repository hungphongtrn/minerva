"""minerva migrate - Run database migrations."""

import argparse
import sys

from alembic.config import Config
from alembic import command


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the migrate subcommand parser."""
    parser = subparsers.add_parser(
        "migrate",
        help="Run database migrations",
        description="Run Alembic migrations to upgrade database schema to latest version",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without executing",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the migrate command.

    Runs `alembic upgrade head` via Python API (not shelling out).
    """
    try:
        alembic_cfg = Config("alembic.ini")

        if args.dry_run:
            # Show current and target revision
            from alembic.script import ScriptDirectory
            from sqlalchemy import text, create_engine

            from src.config.settings import settings

            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()

            engine = create_engine(settings.DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.fetchone()
                current_rev = row[0] if row else "None (uninitialized)"

            print(f"Current revision: {current_rev}")
            print(f"Target revision:  {head_rev}")
            print("\nRun without --dry-run to apply migrations")
            return 0

        # Run migrations
        print(f"Running migrations to revision: {args.revision}")
        command.upgrade(alembic_cfg, args.revision)
        print("✅ Migrations completed successfully")
        return 0

    except Exception as e:
        print(f"❌ Migration failed: {e}", file=sys.stderr)
        return 1
