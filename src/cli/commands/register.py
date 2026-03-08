"""minerva register - Register an agent pack with the system.

Validates agent pack structure, registers it in the database, and syncs
pack files to a Daytona Volume for sandbox mounting.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import get_database_url, settings
from src.db.models import Workspace, User
from src.services.agent_pack_service import AgentPackService
from src.services.agent_pack_validation import AgentPackValidationService
from src.services.daytona_pack_volume_service import (
    DaytonaPackVolumeService,
    PackSyncError,
)


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
        required=False,
        help="Workspace UUID to associate with the pack (optional for OSS - uses default workspace)",
    )
    parser.add_argument(
        "--name",
        help="Human-readable name for the pack (defaults to directory name)",
    )


def _resolve_workspace_id(session, workspace_id_arg: Optional[str]) -> UUID:
    """Resolve workspace ID from argument or find/create default for OSS.

    Args:
        session: Database session
        workspace_id_arg: Workspace ID from command line argument

    Returns:
        Workspace UUID

    Raises:
        ValueError: If workspace cannot be resolved
    """
    # Check if MINERVA_WORKSPACE_ID is set in environment (not "auto")
    env_workspace_id = settings.MINERVA_WORKSPACE_ID

    # If workspace_id is provided via CLI, use that
    if workspace_id_arg:
        try:
            workspace_id = UUID(workspace_id_arg)
            # Verify workspace exists
            workspace = session.query(Workspace).filter(Workspace.id == workspace_id).first()
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")
            return workspace_id
        except ValueError as e:
            raise ValueError(f"Invalid workspace ID: {workspace_id_arg}") from e

    # If MINERVA_WORKSPACE_ID is set and not "auto", validate and use/create it
    if env_workspace_id and env_workspace_id != "auto":
        try:
            workspace_id = UUID(env_workspace_id)
            # Check if workspace exists
            workspace = session.query(Workspace).filter(Workspace.id == workspace_id).first()
            if workspace:
                # Workspace exists - use it
                return workspace_id
            else:
                # Workspace doesn't exist - create it with the specified ID (OSS workflow)
                print(f"Creating workspace with ID: {workspace_id}...")
                from uuid import uuid4

                # Check for existing users
                existing_user = session.query(User).first()
                if existing_user:
                    owner_id = existing_user.id
                    print(f"Using existing user as workspace owner: {owner_id}")
                else:
                    # Create a system user for OSS mode
                    owner_id = uuid4()
                    system_user = User(
                        id=owner_id,
                        email="system@minerva.local",
                        hashed_password="not-used-oss-system-user",
                        is_active=True,
                    )
                    session.add(system_user)
                    session.flush()
                    print(f"Created system user for OSS mode: {owner_id}")

                workspace = Workspace(
                    id=workspace_id,
                    name="OSS Workspace",
                    slug=f"oss-workspace-{str(workspace_id)[:8]}",
                    owner_id=owner_id,
                    is_active=True,
                )
                session.add(workspace)
                session.commit()
                print(f"Created workspace: {workspace_id}")
                return workspace_id
        except ValueError as e:
            raise ValueError(f"Invalid MINERVA_WORKSPACE_ID: {env_workspace_id}") from e

    # No workspace_id provided or "auto" mode - use OSS default behavior
    # For OSS model: look for existing workspaces, use single one if found,
    # or create a default "system" workspace
    workspaces = session.query(Workspace).all()

    if len(workspaces) == 1:
        # Single workspace exists - use it
        print(f"Using existing workspace: {workspaces[0].id}")
        return workspaces[0].id
    elif len(workspaces) > 1:
        # Multiple workspaces - error with list
        print(
            "Multiple workspaces found. Please specify one with --workspace-id:",
            file=sys.stderr,
        )
        for ws in workspaces:
            print(f"  {ws.id} - {ws.name}", file=sys.stderr)
        raise ValueError("Multiple workspaces found. Please specify --workspace-id")
    else:
        # No workspaces exist - create a default system workspace for OSS
        print("Creating default OSS workspace...")
        from uuid import uuid4

        # Check for existing users
        existing_user = session.query(User).first()
        if existing_user:
            owner_id = existing_user.id
            print(f"Using existing user as workspace owner: {owner_id}")
        else:
            # Create a system user for OSS mode
            owner_id = uuid4()
            system_user = User(
                id=owner_id,
                email="system@minerva.local",
                hashed_password="not-used-oss-system-user",
                is_active=True,
            )
            session.add(system_user)
            session.flush()
            print(f"Created system user for OSS mode: {owner_id}")

        workspace = Workspace(
            id=uuid4(),
            name="Default OSS Workspace",
            slug="default-oss-workspace",
            owner_id=owner_id,
            is_active=True,
        )
        session.add(workspace)
        session.commit()
        print(f"Created default workspace: {workspace.id}")
        return workspace.id


def _update_env_file(workspace_id: UUID) -> bool:
    """Update .env file with MINERVA_WORKSPACE_ID.

    Args:
        workspace_id: The workspace ID to set in .env

    Returns:
        True if .env was updated, False otherwise
    """
    env_path = Path(".env")

    if not env_path.exists():
        return False

    try:
        content = env_path.read_text()

        # Check if MINERVA_WORKSPACE_ID exists in file
        if "MINERVA_WORKSPACE_ID" in content:
            # Replace existing value (including "auto" or empty)
            # Match MINERVA_WORKSPACE_ID=... until end of line or comment
            pattern = r"(MINERVA_WORKSPACE_ID=).*?$"
            replacement = rf"\g<1>{workspace_id}"
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

            if new_content != content:
                env_path.write_text(new_content)
                return True
        else:
            # Add MINERVA_WORKSPACE_ID to end of file
            with open(env_path, "a") as f:
                f.write(f"\n# Auto-generated by minerva register\n")
                f.write(f"MINERVA_WORKSPACE_ID={workspace_id}\n")
            return True

    except Exception as e:
        print(f"Warning: Could not update .env file: {e}", file=sys.stderr)

    return False


async def _sync_pack_volume(
    pack_id: UUID, source_path: str, source_digest: str, snapshot_name: str
) -> None:
    """Sync pack files to Daytona Volume.

    Args:
        pack_id: Agent pack UUID
        source_path: Local filesystem path to pack directory
        source_digest: SHA-256 digest of pack content
        snapshot_name: Daytona snapshot name for disposable sandboxes

    Raises:
        PackSyncError: If sync fails
    """
    volume_service = DaytonaPackVolumeService(
        api_key=settings.DAYTONA_API_KEY,
        api_url=settings.DAYTONA_API_URL,
        target=settings.DAYTONA_TARGET,
        snapshot_name=snapshot_name,
    )
    await volume_service.sync_pack_to_volume(
        pack_id=pack_id,
        source_path=source_path,
        source_digest=source_digest,
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the register command.

    Validates pack structure, registers in DB, and syncs to volume.

    Exit codes:
        0: Success
        1: Validation error
        2: Database error
        3: Volume sync error
    """
    # Resolve pack path
    pack_path = Path(args.path).resolve()

    if not pack_path.exists():
        print(f"Error: Pack path does not exist: {pack_path}", file=sys.stderr)
        return 1

    if not pack_path.is_dir():
        print(f"Error: Pack path is not a directory: {pack_path}", file=sys.stderr)
        return 1

    # Determine pack name
    pack_name = args.name or pack_path.name

    # Step 1: Validate pack structure
    print(f"Validating pack at {pack_path}...")
    validation_service = AgentPackValidationService()
    report = validation_service.validate(str(pack_path), compute_digest=True)

    if not report.is_valid:
        print(
            f"\nValidation failed with {report.error_count} error(s):\n",
            file=sys.stderr,
        )
        for entry in report.checklist:
            if entry.severity == "error":
                print(f"  ✗ {entry.path}: {entry.message}", file=sys.stderr)
        return 1

    print(f"✓ Pack structure is valid")
    if report.warning_count > 0:
        print(f"  Warnings: {report.warning_count}")

    # Step 2: Register in database
    try:
        engine = create_engine(get_database_url())
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Resolve workspace ID (may create default for OSS)
            try:
                workspace_id = _resolve_workspace_id(session, args.workspace_id)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2

            print(f"\nRegistering pack '{pack_name}' in workspace {workspace_id}...")

            pack_service = AgentPackService(session)
            result = pack_service.register(
                workspace_id=workspace_id,
                name=pack_name,
                source_path=str(pack_path),
            )

            if not result.success:
                print(f"\nRegistration failed:", file=sys.stderr)
                for error in result.errors:
                    print(f"  {error}", file=sys.stderr)
                return 2

            pack = result.pack
            print(f"✓ Pack registered with ID: {pack.id}")

            # Commit the transaction to persist the pack
            session.commit()
            print(f"✓ Committed pack to database")

            # Step 3: Sync pack files to Daytona Volume
            print(f"\nSyncing pack files to Daytona Volume...")

            try:
                asyncio.run(
                    _sync_pack_volume(
                        pack_id=pack.id,
                        source_path=str(pack_path),
                        source_digest=pack.source_digest,
                        snapshot_name=settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME,
                    )
                )
                print(f"✓ Pack files synced to volume")

                # Try to auto-update .env file
                env_updated = _update_env_file(workspace_id)

                # Success!
                print(f"\n{'=' * 60}")
                print(f"Pack registered successfully!")
                print(f"{'=' * 60}")
                print(f"  Workspace ID: {workspace_id}")
                print(f"  Pack ID: {pack.id}")
                print(f"  Name: {pack.name}")
                print(f"  Digest: {pack.source_digest[:16]}...")
                print(f"  Path: {pack.source_path}")
                if env_updated:
                    print(f"\n✓ Updated .env file with MINERVA_WORKSPACE_ID")
                else:
                    print(f"\nAdd this to your .env file:")
                    print(f"  MINERVA_WORKSPACE_ID={workspace_id}")
                print(f"\nUse this pack ID as the deployment default:")
                print(f"  --agent-pack-id {pack.id}")
                print(f"{'=' * 60}")

                return 0

            except PackSyncError as e:
                print(f"\n✗ Volume sync failed: {e}", file=sys.stderr)
                print(
                    f"\nThe pack was registered in the database but volume sync failed.",
                    file=sys.stderr,
                )
                print(f"You can retry sync by re-running this command.", file=sys.stderr)
                return 3
            except Exception as e:
                print(f"\n✗ Unexpected error during volume sync: {e}", file=sys.stderr)
                return 3

        finally:
            session.close()

    except Exception as e:
        print(f"\n✗ Database error: {e}", file=sys.stderr)
        return 2
