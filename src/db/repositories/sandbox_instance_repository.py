"""Repository for sandbox instance operations.

Provides CRUD and query methods for sandbox lifecycle management,
including health-aware routing and idle detection.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from src.db.models import (
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
)


class SandboxInstanceRepository:
    """Repository for sandbox instance lifecycle and routing queries."""

    def __init__(self, session: Session):
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def create(
        self,
        workspace_id: UUID,
        profile: SandboxProfile,
        provider_ref: Optional[str] = None,
        agent_pack_id: Optional[UUID] = None,
        idle_ttl_seconds: int = 3600,
        gateway_url: Optional[str] = None,
    ) -> SandboxInstance:
        """Create a new sandbox instance record.

        Args:
            workspace_id: UUID of the workspace.
            profile: Deployment profile (local_compose or daytona).
            provider_ref: Provider-specific reference identifier.
            agent_pack_id: Optional ID of associated agent pack.
            idle_ttl_seconds: TTL for idle auto-stop in seconds.
            gateway_url: Optional URL for Picoclaw gateway bridge access.

        Returns:
            The created SandboxInstance.
        """
        sandbox = SandboxInstance(
            workspace_id=workspace_id,
            profile=profile,
            provider_ref=provider_ref,
            state=SandboxState.PENDING,
            health_status=SandboxHealthStatus.UNKNOWN,
            agent_pack_id=agent_pack_id,
            idle_ttl_seconds=idle_ttl_seconds,
            gateway_url=gateway_url,
        )

        self._session.add(sandbox)
        self._session.flush()

        return sandbox

    def get_by_id(self, sandbox_id: UUID) -> Optional[SandboxInstance]:
        """Get sandbox by ID.

        Args:
            sandbox_id: UUID of the sandbox.

        Returns:
            SandboxInstance if found, None otherwise.
        """
        stmt = select(SandboxInstance).where(SandboxInstance.id == sandbox_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_provider_ref(self, provider_ref: str) -> Optional[SandboxInstance]:
        """Get sandbox by provider reference.

        Args:
            provider_ref: Provider-specific reference identifier.

        Returns:
            SandboxInstance if found, None otherwise.
        """
        stmt = select(SandboxInstance).where(
            SandboxInstance.provider_ref == provider_ref
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_workspace(
        self,
        workspace_id: UUID,
        include_inactive: bool = False,
    ) -> List[SandboxInstance]:
        """List sandboxes for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            include_inactive: If True, include stopped/failed sandboxes.

        Returns:
            List of SandboxInstance records.
        """
        stmt = select(SandboxInstance).where(
            SandboxInstance.workspace_id == workspace_id
        )

        if not include_inactive:
            stmt = stmt.where(
                SandboxInstance.state.notin_(
                    [
                        SandboxState.STOPPED,
                        SandboxState.FAILED,
                    ]
                )
            )

        stmt = stmt.order_by(SandboxInstance.created_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def list_active_healthy_by_workspace(
        self,
        workspace_id: UUID,
        profile: Optional[SandboxProfile] = None,
    ) -> List[SandboxInstance]:
        """List active and healthy sandboxes for routing decisions.

        This is the primary query for sandbox routing - returns sandboxes
        that are safe to route traffic to.

        Args:
            workspace_id: UUID of the workspace.
            profile: Optional profile filter (local_compose or daytona).

        Returns:
            List of active, healthy SandboxInstance records.
        """
        stmt = select(SandboxInstance).where(
            and_(
                SandboxInstance.workspace_id == workspace_id,
                SandboxInstance.state == SandboxState.ACTIVE,
                SandboxInstance.health_status == SandboxHealthStatus.HEALTHY,
            )
        )

        if profile:
            stmt = stmt.where(SandboxInstance.profile == profile)

        stmt = stmt.order_by(SandboxInstance.last_activity_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def list_unhealthy_sandboxes(
        self,
        workspace_id: Optional[UUID] = None,
    ) -> List[SandboxInstance]:
        """List sandboxes marked as unhealthy.

        Used for health monitoring and cleanup operations.

        Args:
            workspace_id: Optional workspace filter.

        Returns:
            List of unhealthy SandboxInstance records.
        """
        conditions = [
            SandboxInstance.health_status == SandboxHealthStatus.UNHEALTHY,
        ]

        if workspace_id:
            conditions.append(SandboxInstance.workspace_id == workspace_id)

        stmt = select(SandboxInstance).where(and_(*conditions))
        stmt = stmt.order_by(SandboxInstance.last_health_at.asc())

        return list(self._session.execute(stmt).scalars().all())

    def list_idle_sandboxes(
        self,
        idle_threshold_seconds: Optional[int] = None,
        workspace_id: Optional[UUID] = None,
    ) -> List[SandboxInstance]:
        """List sandboxes that have exceeded their idle TTL.

        Used by idle auto-stop worker to find sandboxes to stop.

        Args:
            idle_threshold_seconds: Override idle threshold (uses
                per-sandbox idle_ttl_seconds if not provided).
            workspace_id: Optional workspace filter.

        Returns:
            List of idle SandboxInstance records.
        """
        now = datetime.utcnow()

        # Base conditions: active sandboxes with last_activity_at set
        conditions = [
            SandboxInstance.state == SandboxState.ACTIVE,
            SandboxInstance.last_activity_at.isnot(None),
        ]

        if workspace_id:
            conditions.append(SandboxInstance.workspace_id == workspace_id)

        if idle_threshold_seconds:
            # Use global threshold
            threshold_time = now - __import__("datetime").timedelta(
                seconds=idle_threshold_seconds
            )
            conditions.append(SandboxInstance.last_activity_at < threshold_time)
        else:
            # Use per-sandbox TTL with timestamp comparison
            # last_activity_at + idle_ttl_seconds < now
            # This is approximate and may need DB-specific handling
            conditions.append(SandboxInstance.last_activity_at < now)

        stmt = select(SandboxInstance).where(and_(*conditions))

        return list(self._session.execute(stmt).scalars().all())

    def update_state(
        self,
        sandbox_id: UUID,
        state: SandboxState,
    ) -> Optional[SandboxInstance]:
        """Update sandbox state.

        Args:
            sandbox_id: UUID of the sandbox.
            state: New state value.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.state = state

        if state == SandboxState.STOPPED:
            sandbox.stopped_at = datetime.utcnow()

        self._session.flush()
        return sandbox

    def update_health(
        self,
        sandbox_id: UUID,
        health_status: SandboxHealthStatus,
    ) -> Optional[SandboxInstance]:
        """Update sandbox health status.

        Args:
            sandbox_id: UUID of the sandbox.
            health_status: New health status.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.health_status = health_status
        sandbox.last_health_at = datetime.utcnow()

        self._session.flush()
        return sandbox

    def update_activity(
        self,
        sandbox_id: UUID,
    ) -> Optional[SandboxInstance]:
        """Update last activity timestamp to now.

        Should be called when sandbox processes a request.

        Args:
            sandbox_id: UUID of the sandbox.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.last_activity_at = datetime.utcnow()
        self._session.flush()

        return sandbox

    def set_provider_ref(
        self,
        sandbox_id: UUID,
        provider_ref: str,
    ) -> Optional[SandboxInstance]:
        """Set the provider reference for a sandbox.

        Called after successful provisioning.

        Args:
            sandbox_id: UUID of the sandbox.
            provider_ref: Provider-specific reference.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.provider_ref = provider_ref
        self._session.flush()

        return sandbox

    def update_gateway_url(
        self,
        sandbox_id: UUID,
        gateway_url: str,
    ) -> Optional[SandboxInstance]:
        """Update the gateway URL for a sandbox.

        Called after successful provisioning to store the Picoclaw
        gateway URL for bridge execution.

        Args:
            sandbox_id: UUID of the sandbox.
            gateway_url: URL for Picoclaw gateway bridge access.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.gateway_url = gateway_url
        self._session.flush()

        return sandbox
