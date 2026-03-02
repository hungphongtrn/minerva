"""minerva register - Register an agent pack with the system.

Validates agent pack structure, registers it in the database, and syncs
pack files to a Daytona Volume for sandbox mounting.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.database import get_database_url
from src.services.agent_pack_service import AgentPackService
from src.services.agent_pack_validation import AgentPackValidationService
from src.services.daytona_pack_volume_service import DaytonaPackVolumeService, PackSyncError


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
    parser.add_argument(
        "--name",
        help="Human-readable name for the pack (defaults to directory name)",
    )


async def _sync_pack_volume(pack_id: UUID, source_path: str, source_digest: str) -> None:
    """Sync pack files to Daytona Volume.
    
    Args:
        pack_id: Agent pack UUID
        source_path: Local filesystem path to pack directory
        source_digest: SHA-256 digest of pack content
        
    Raises:
        PackSyncError: If sync fails
    """
    volume_service = DaytonaPackVolumeService()
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
    
    # Parse workspace ID
    try:
        workspace_id = UUID(args.workspace_id)
    except ValueError:
        print(f"Error: Invalid workspace ID: {args.workspace_id}", file=sys.stderr)
        return 1
    
    # Step 1: Validate pack structure
    print(f"Validating pack at {pack_path}...")
    validation_service = AgentPackValidationService()
    report = validation_service.validate(str(pack_path), compute_digest=True)
    
    if not report.is_valid:
        print(f"\nValidation failed with {report.error_count} error(s):\n", file=sys.stderr)
        for entry in report.checklist:
            if entry.severity == "error":
                print(f"  ✗ {entry.path}: {entry.message}", file=sys.stderr)
        return 1
    
    print(f"✓ Pack structure is valid")
    if report.warning_count > 0:
        print(f"  Warnings: {report.warning_count}")
    
    # Step 2: Register in database
    print(f"\nRegistering pack '{pack_name}' in workspace {workspace_id}...")
    
    try:
        engine = create_engine(get_database_url())
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
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
            
            # Step 3: Sync pack files to Daytona Volume
            print(f"\nSyncing pack files to Daytona Volume...")
            
            try:
                asyncio.run(_sync_pack_volume(
                    pack_id=pack.id,
                    source_path=str(pack_path),
                    source_digest=pack.source_digest,
                ))
                print(f"✓ Pack files synced to volume")
                
                # Success!
                print(f"\n{'='*60}")
                print(f"Pack registered successfully!")
                print(f"{'='*60}")
                print(f"  Pack ID: {pack.id}")
                print(f"  Name: {pack.name}")
                print(f"  Digest: {pack.source_digest[:16]}...")
                print(f"  Path: {pack.source_path}")
                print(f"\nUse this pack ID as the deployment default:")
                print(f"  --agent-pack-id {pack.id}")
                print(f"{'='*60}")
                
                return 0
                
            except PackSyncError as e:
                print(f"\n✗ Volume sync failed: {e}", file=sys.stderr)
                print(f"\nThe pack was registered in the database but volume sync failed.", file=sys.stderr)
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
