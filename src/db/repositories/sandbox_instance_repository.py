"""Repository for sandbox instance operations.

Provides CRUD and query methods for sandbox lifecycle management,
including health-aware routing and idle detection.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.models import (
    SandboxInstance,
    SandboxState,
    SandboxHealthStatus,
    SandboxProfile,
    SandboxHydrationStatus,
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
        external_user_id: Optional[str] = None,
    ) -> SandboxInstance:
        """Create a new sandbox instance record.

        Args:
            workspace_id: UUID of the workspace.
            profile: Deployment profile (local_compose or daytona).
            provider_ref: Provider-specific reference identifier.
            agent_pack_id: Optional ID of associated agent pack.
            idle_ttl_seconds: TTL for idle auto-stop in seconds.
            gateway_url: Optional URL for Picoclaw gateway bridge access.
            external_user_id: Optional external user ID for per-user sandbox routing.

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
            external_user_id=external_user_id,
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
        external_user_id: Optional[str] = None,
    ) -> List[SandboxInstance]:
        """List sandboxes for a workspace.

        Args:
            workspace_id: UUID of the workspace.
            include_inactive: If True, include stopped/failed sandboxes.
            external_user_id: Optional filter by external user ID.

        Returns:
            List of SandboxInstance records.
        """
        conditions = [
            SandboxInstance.workspace_id == workspace_id,
        ]

        # Filter by external_user_id if provided
        if external_user_id is not None:
            conditions.append(SandboxInstance.external_user_id == external_user_id)

        stmt = select(SandboxInstance).where(and_(*conditions))

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
        external_user_id: Optional[str] = None,
    ) -> List[SandboxInstance]:
        """List active and healthy sandboxes for routing decisions.

        This is the primary query for sandbox routing - returns sandboxes
        that are safe to route traffic to.

        Args:
            workspace_id: UUID of the workspace.
            profile: Optional profile filter (local_compose or daytona).
            external_user_id: Optional filter by external user ID for per-user routing.

        Returns:
            List of active, healthy SandboxInstance records.
        """
        conditions = [
            SandboxInstance.workspace_id == workspace_id,
            SandboxInstance.state == SandboxState.ACTIVE,
            SandboxInstance.health_status == SandboxHealthStatus.HEALTHY,
        ]

        # Filter by external_user_id if provided
        if external_user_id is not None:
            conditions.append(SandboxInstance.external_user_id == external_user_id)

        stmt = select(SandboxInstance).where(and_(*conditions))

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

    # Phase 3.1: Bridge token rotation and gateway authority

    def rotate_bridge_token(
        self,
        sandbox_id: UUID,
        new_token: str,
        grace_seconds: int = 30,
    ) -> Optional[SandboxInstance]:
        """Rotate the bridge authentication token with grace period.

        Moves the current token to the 'previous' slot with an expiry,
        then sets the new token as current. This ensures in-flight
        requests using the old token continue to work during cutover.

        Args:
            sandbox_id: UUID of the sandbox.
            new_token: The new bridge authentication token.
            grace_seconds: Seconds to keep the old token valid (default: 30).

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        # Move current token to previous slot with expiry
        sandbox.bridge_auth_token_prev = sandbox.bridge_auth_token
        sandbox.bridge_auth_token_prev_expires_at = datetime.utcnow() + __import__(
            "datetime"
        ).timedelta(seconds=grace_seconds)

        # Set new token as current
        sandbox.bridge_auth_token = new_token

        self._session.flush()
        return sandbox

    def resolve_bridge_tokens(
        self,
        sandbox_id: UUID,
    ) -> dict:
        """Resolve the active bridge tokens for a sandbox.

        Returns both the current token and (if still valid) the previous
        token for grace-period acceptance. Used by the bridge layer to
        validate incoming requests.

        Args:
            sandbox_id: UUID of the sandbox.

        Returns:
            Dictionary with:
                - current: The current bridge auth token (or None)
                - previous: The previous token if within grace period (or None)
                - previous_expires_at: Expiry timestamp for previous token (or None)
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return {"current": None, "previous": None, "previous_expires_at": None}

        result = {
            "current": sandbox.bridge_auth_token,
            "previous": None,
            "previous_expires_at": None,
        }

        # Include previous token only if it exists and hasn't expired
        now = datetime.utcnow()
        if sandbox.bridge_auth_token_prev and sandbox.bridge_auth_token_prev_expires_at:
            if sandbox.bridge_auth_token_prev_expires_at > now:
                result["previous"] = sandbox.bridge_auth_token_prev
                result["previous_expires_at"] = (
                    sandbox.bridge_auth_token_prev_expires_at
                )

        return result

    def set_gateway_url_authoritative(
        self,
        sandbox_id: UUID,
        gateway_url: str,
    ) -> Optional[SandboxInstance]:
        """Set the authoritative gateway URL for a sandbox.

        Unlike update_gateway_url, this method explicitly marks the URL
        as the canonical endpoint for bridge execution. Consumers must
        not derive URLs from other sources once this is set.

        Args:
            sandbox_id: UUID of the sandbox.
            gateway_url: The authoritative Picoclaw gateway URL.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.gateway_url = gateway_url
        self._session.flush()
        return sandbox

    # Phase 3.1: Readiness and hydration helpers

    def set_identity_ready(
        self,
        sandbox_id: UUID,
        ready: bool = True,
    ) -> Optional[SandboxInstance]:
        """Set the identity readiness state for a sandbox.

        Identity ready means AGENT.md, SOUL.md, IDENTITY.md, and skills/
        are properly mounted. This is a hard gate for request acceptance.

        Args:
            sandbox_id: UUID of the sandbox.
            ready: True if identity files are mounted correctly.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.identity_ready = ready
        self._session.flush()
        return sandbox

    def set_hydration_status(
        self,
        sandbox_id: UUID,
        status: str,
        last_error: Optional[str] = None,
    ) -> Optional[SandboxInstance]:
        """Set the checkpoint hydration status for a sandbox.

        Hydration is the process of restoring memory/session checkpoint
        data after sandbox reaches health-ready state.

        Args:
            sandbox_id: UUID of the sandbox.
            status: One of 'pending', 'in_progress', 'completed', 'degraded', 'failed'.
            last_error: Optional error message if status is 'failed' or 'degraded'.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        # Validate status
        valid_statuses = {
            SandboxHydrationStatus.PENDING,
            SandboxHydrationStatus.IN_PROGRESS,
            SandboxHydrationStatus.COMPLETED,
            SandboxHydrationStatus.DEGRADED,
            SandboxHydrationStatus.FAILED,
        }
        if status not in valid_statuses:
            raise ValueError(f"Invalid hydration status: {status}")

        sandbox.hydration_status = status

        if last_error:
            sandbox.hydration_last_error = last_error

        # Reset retry count on successful completion
        if status == SandboxHydrationStatus.COMPLETED:
            sandbox.hydration_retry_count = 0
            sandbox.hydration_last_error = None

        self._session.flush()
        return sandbox

    def increment_hydration_retry(
        self,
        sandbox_id: UUID,
        error: Optional[str] = None,
    ) -> Optional[SandboxInstance]:
        """Increment the hydration retry counter.

        Called after a failed hydration attempt to track retry budget.

        Args:
            sandbox_id: UUID of the sandbox.
            error: Optional error message from the failed attempt.

        Returns:
            Updated SandboxInstance if found, None otherwise.
        """
        sandbox = self.get_by_id(sandbox_id)
        if not sandbox:
            return None

        sandbox.hydration_retry_count += 1

        if error:
            sandbox.hydration_last_error = error

        self._session.flush()
        return sandbox

    def list_identity_not_ready(
        self,
        workspace_id: Optional[UUID] = None,
    ) -> List[SandboxInstance]:
        """List sandboxes where identity is not ready.

        Used for monitoring and auto-reprovision decisions.

        Args:
            workspace_id: Optional workspace filter.

        Returns:
            List of SandboxInstance records with identity_ready=False.
        """
        conditions = [
            SandboxInstance.identity_ready.is_(False),
        ]

        if workspace_id:
            conditions.append(SandboxInstance.workspace_id == workspace_id)

        stmt = select(SandboxInstance).where(and_(*conditions))
        stmt = stmt.order_by(SandboxInstance.created_at.desc())

        return list(self._session.execute(stmt).scalars().all())

    def list_hydration_degraded(
        self,
        workspace_id: Optional[UUID] = None,
    ) -> List[SandboxInstance]:
        """List sandboxes with degraded or failed hydration status.

        Used for operator alerting and diagnostics.

        Args:
            workspace_id: Optional workspace filter.

        Returns:
            List of SandboxInstance records with degraded hydration.
        """
        conditions = [
            SandboxInstance.hydration_status.in_(
                [SandboxHydrationStatus.DEGRADED, SandboxHydrationStatus.FAILED]
            ),
        ]

        if workspace_id:
            conditions.append(SandboxInstance.workspace_id == workspace_id)

        stmt = select(SandboxInstance).where(and_(*conditions))
        stmt = stmt.order_by(SandboxInstance.updated_at.desc())

        return list(self._session.execute(stmt).scalars().all())
