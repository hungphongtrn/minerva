"""Database models for identity, policy, and workspace lifecycle."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
    Text,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID

from src.db.session import Base


# Phase 2: Workspace Lifecycle and Agent Pack Enums
class WorkspaceLeaseState:
    """States for workspace lease lifecycle."""

    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


class SandboxState:
    """States for sandbox instance lifecycle."""

    PENDING = "pending"
    CREATING = "creating"
    ACTIVE = "active"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class SandboxHealthStatus:
    """Health assessment for sandbox instances."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class SandboxProfile:
    """Deployment profiles for sandbox instances."""

    LOCAL_COMPOSE = "local_compose"
    DAYTONA = "daytona"


class AgentPackValidationStatus:
    """Validation states for agent pack registration."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_guest = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Workspace(Base):
    """Workspace/tenant model for multi-tenancy."""

    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Membership(Base):
    """Workspace membership linking users to workspaces."""

    __tablename__ = "memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    role = Column(
        Enum("owner", "admin", "member", name="membership_role"),
        default="member",
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ApiKey(Base):
    """API key model for workspace authentication."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False)
    scopes = Column(Text, default="", nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class WorkspaceResource(Base):
    """Base model for workspace-scoped resources with tenant isolation."""

    __tablename__ = "workspace_resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    resource_type = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    config = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


# Phase 2 Models: Workspace Lifecycle and Agent Pack Portability


class WorkspaceLease(Base):
    """Lease record for workspace write serialization.

    Enforces one active writer per workspace at any time.
    Lease expiration prevents deadlocks from crashed writers.
    """

    __tablename__ = "workspace_leases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Lease holder identification
    holder_run_id = Column(String(255), nullable=True)
    holder_identity = Column(String(255), nullable=True)

    # Lease lifecycle
    acquired_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime, nullable=True)

    # Optimistic locking for lease operations
    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class SandboxInstance(Base):
    """Sandbox instance state for workspace execution environments.

    Tracks health, activity, and lifecycle for deterministic routing decisions.
    """

    __tablename__ = "sandbox_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Deployment profile (local_compose | daytona)
    profile = Column(
        Enum(
            SandboxProfile.LOCAL_COMPOSE,
            SandboxProfile.DAYTONA,
            name="sandbox_profile",
        ),
        nullable=False,
    )

    # Provider-specific reference (e.g., Daytona sandbox ID)
    provider_ref = Column(String(255), nullable=True)

    # Lifecycle state
    state = Column(
        Enum(
            SandboxState.PENDING,
            SandboxState.CREATING,
            SandboxState.ACTIVE,
            SandboxState.UNHEALTHY,
            SandboxState.STOPPING,
            SandboxState.STOPPED,
            SandboxState.FAILED,
            name="sandbox_state",
        ),
        default=SandboxState.PENDING,
        nullable=False,
    )

    # Health assessment
    health_status = Column(
        Enum(
            SandboxHealthStatus.HEALTHY,
            SandboxHealthStatus.UNHEALTHY,
            SandboxHealthStatus.UNKNOWN,
            name="sandbox_health_status",
        ),
        default=SandboxHealthStatus.UNKNOWN,
        nullable=False,
    )
    last_health_at = Column(DateTime, nullable=True)

    # Activity tracking for idle TTL enforcement
    last_activity_at = Column(DateTime, nullable=True)
    idle_ttl_seconds = Column(Integer, default=3600, nullable=False)

    # Optional: Link to agent pack for this sandbox
    agent_pack_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_packs.id", ondelete="SET NULL"),
        nullable=True,
    )

    stopped_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AgentPack(Base):
    """Registered agent pack metadata linked to source filesystem path.

    Supports path-linked registration where the folder remains the source of truth.
    Auto-detects stale packs when source digest changes.
    """

    __tablename__ = "agent_packs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Pack identification
    name = Column(String(255), nullable=False)

    # Path-linked source (folder is source of truth)
    source_path = Column(String(512), nullable=False)
    source_digest = Column(String(64), nullable=True)

    # Activation state
    is_active = Column(Boolean, default=True, nullable=False)

    # Validation state
    last_validated_at = Column(DateTime, nullable=True)
    validation_status = Column(
        Enum(
            AgentPackValidationStatus.PENDING,
            AgentPackValidationStatus.VALID,
            AgentPackValidationStatus.INVALID,
            AgentPackValidationStatus.STALE,
            name="agent_pack_validation_status",
        ),
        default=AgentPackValidationStatus.PENDING,
        nullable=False,
    )
    validation_report_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AgentPackRevision(Base):
    """Revision history for agent pack source changes.

    Tracks detected changes with digests for audit and rollback support.
    """

    __tablename__ = "agent_pack_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_pack_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_packs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Source state at detection time
    source_digest = Column(String(64), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Optional change summary
    change_summary_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
