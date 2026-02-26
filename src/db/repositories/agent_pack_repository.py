"""Repository for agent pack operations.

Provides CRUD and query methods for agent pack registration,
validation state management, and revision tracking.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.models import (
    AgentPack,
    AgentPackRevision,
    AgentPackValidationStatus,
)


class AgentPackRepository:
    """Repository for agent pack lifecycle and validation operations."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        workspace_id: UUID,
        name: str,
        source_path: str,
        source_digest: Optional[str] = None,
    ) -> AgentPack:
        """Register a new agent pack.

        Args:
            workspace_id: UUID of the owning workspace.
            name: Human-readable name for the pack.
            source_path: Filesystem path to the pack folder.
            source_digest: Optional initial source digest.

        Returns:
            The created AgentPack.

        Raises:
            IntegrityError: If pack with same workspace+path already exists.
        """
        pack = AgentPack(
            workspace_id=workspace_id,
            name=name,
            source_path=source_path,
            source_digest=source_digest,
            validation_status=AgentPackValidationStatus.PENDING,
        )

        self._session.add(pack)
        self._session.flush()

        return pack

    def get_by_id(self, pack_id: UUID) -> Optional[AgentPack]:
        """Get agent pack by ID.

        Args:
            pack_id: UUID of the agent pack.

        Returns:
            AgentPack if found, None otherwise.
        """
        stmt = select(AgentPack).where(AgentPack.id == pack_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_workspace_and_path(
        self,
        workspace_id: UUID,
        source_path: str,
    ) -> Optional[AgentPack]:
        """Get agent pack by workspace and source path.

        Args:
            workspace_id: UUID of the workspace.
            source_path: Filesystem path to the pack folder.

        Returns:
            AgentPack if found, None otherwise.
        """
        stmt = select(AgentPack).where(
            and_(
                AgentPack.workspace_id == workspace_id,
                AgentPack.source_path == source_path,
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        include_inactive: bool = False,
    ) -> List[AgentPack]:
        """List agent packs for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            include_inactive: If True, include inactive packs.

        Returns:
            List of AgentPack records.
        """
        stmt = select(AgentPack).where(AgentPack.workspace_id == workspace_id)

        if not include_inactive:
            stmt = stmt.where(AgentPack.is_active)

        stmt = stmt.order_by(AgentPack.created_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def list_by_validation_status(
        self,
        status: AgentPackValidationStatus,
        workspace_id: Optional[UUID] = None,
    ) -> List[AgentPack]:
        """List agent packs filtered by validation status.

        Args:
            status: Validation status to filter by.
            workspace_id: Optional workspace filter.

        Returns:
            List of AgentPack records.
        """
        conditions = [AgentPack.validation_status == status]

        if workspace_id:
            conditions.append(AgentPack.workspace_id == workspace_id)

        stmt = select(AgentPack).where(and_(*conditions))
        stmt = stmt.order_by(AgentPack.last_validated_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def list_stale_packs(
        self,
        workspace_id: Optional[UUID] = None,
    ) -> List[AgentPack]:
        """List packs that are marked as stale (source changed).

        Args:
            workspace_id: Optional workspace filter.

        Returns:
            List of stale AgentPack records.
        """
        return self.list_by_validation_status(
            AgentPackValidationStatus.STALE,
            workspace_id,
        )

    def update_validation_status(
        self,
        pack_id: UUID,
        status: AgentPackValidationStatus,
        report_json: Optional[str] = None,
    ) -> Optional[AgentPack]:
        """Update pack validation status.

        Args:
            pack_id: UUID of the agent pack.
            status: New validation status.
            report_json: Optional JSON validation report.

        Returns:
            Updated AgentPack if found, None otherwise.
        """
        pack = self.get_by_id(pack_id)
        if not pack:
            return None

        pack.validation_status = status
        pack.last_validated_at = datetime.utcnow()

        if report_json is not None:
            pack.validation_report_json = report_json

        self._session.flush()
        return pack

    def update_source_digest(
        self,
        pack_id: UUID,
        source_digest: str,
        mark_stale: bool = False,
    ) -> Optional[AgentPack]:
        """Update pack source digest.

        Args:
            pack_id: UUID of the agent pack.
            source_digest: New source digest.
            mark_stale: If True, mark pack as stale if digest changed.

        Returns:
            Updated AgentPack if found, None otherwise.
        """
        pack = self.get_by_id(pack_id)
        if not pack:
            return None

        if mark_stale and pack.source_digest != source_digest:
            pack.validation_status = AgentPackValidationStatus.STALE

        pack.source_digest = source_digest
        self._session.flush()

        return pack

    def set_active(
        self,
        pack_id: UUID,
        is_active: bool,
    ) -> Optional[AgentPack]:
        """Set pack active/inactive status.

        Args:
            pack_id: UUID of the agent pack.
            is_active: New active status.

        Returns:
            Updated AgentPack if found, None otherwise.
        """
        pack = self.get_by_id(pack_id)
        if not pack:
            return None

        pack.is_active = is_active
        self._session.flush()

        return pack

    def add_revision(
        self,
        pack_id: UUID,
        source_digest: str,
        change_summary_json: Optional[str] = None,
    ) -> AgentPackRevision:
        """Record a new revision for an agent pack.

        Args:
            pack_id: UUID of the agent pack.
            source_digest: Source digest at this revision.
            change_summary_json: Optional JSON change summary.

        Returns:
            The created AgentPackRevision.
        """
        revision = AgentPackRevision(
            agent_pack_id=pack_id,
            source_digest=source_digest,
            change_summary_json=change_summary_json,
        )

        self._session.add(revision)
        self._session.flush()

        return revision

    def get_revisions(
        self,
        pack_id: UUID,
        limit: int = 10,
    ) -> List[AgentPackRevision]:
        """Get revision history for a pack.

        Args:
            pack_id: UUID of the agent pack.
            limit: Maximum number of revisions to return.

        Returns:
            List of AgentPackRevision records, most recent first.
        """
        stmt = (
            select(AgentPackRevision)
            .where(AgentPackRevision.agent_pack_id == pack_id)
            .order_by(AgentPackRevision.detected_at.desc())
            .limit(limit)
        )

        return list(self._session.execute(stmt).scalars().all())

    def is_registered(
        self,
        workspace_id: UUID,
        source_path: str,
    ) -> bool:
        """Check if a pack is already registered for workspace+path.

        Args:
            workspace_id: UUID of the workspace.
            source_path: Filesystem path to the pack folder.

        Returns:
            True if pack exists, False otherwise.
        """
        return self.get_by_workspace_and_path(workspace_id, source_path) is not None
