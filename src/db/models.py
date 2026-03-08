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
    UniqueConstraint,
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


class SandboxHydrationStatus:
    """Hydration status for checkpoint restoration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


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


# Phase 3: Persistence and Checkpoint Recovery Enums
class RunSessionState:
    """States for run session lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeEventType:
    """Types of runtime events for audit and observability."""

    # Lifecycle events
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
    SESSION_CANCELLED = "session_cancelled"

    # Checkpoint events
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORE_STARTED = "checkpoint_restore_started"
    CHECKPOINT_RESTORE_COMPLETED = "checkpoint_restore_completed"
    CHECKPOINT_RESTORE_FAILED = "checkpoint_restore_failed"
    CHECKPOINT_FALLBACK_USED = "checkpoint_fallback_used"

    # Policy/Security events
    POLICY_VIOLATION = "policy_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class CheckpointState:
    """States for checkpoint lifecycle."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AuditEventCategory:
    """Categories for audit events."""

    RUN_EXECUTION = "run_execution"
    CHECKPOINT_MANAGEMENT = "checkpoint_management"
    POLICY_ENFORCEMENT = "policy_enforcement"
    SYSTEM_OPERATION = "system_operation"


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


class ExternalIdentity(Base):
    """External identity for OSS end-user requests.

    Completely separate from the developer users table.
    Scoped to the developer's workspace via composite key.
    """

    __tablename__ = "external_identities"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), primary_key=True)
    external_user_id = Column(String(255), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Composite unique constraint for workspace-scoped uniqueness
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "external_user_id",
            name="uq_external_identity_workspace_user",
        ),
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
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
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
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
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
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
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

    # External user ID for per-user sandbox routing (OSS mode)
    external_user_id = Column(String(255), nullable=True)

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

    # Picoclaw gateway URL for bridge execution
    gateway_url = Column(String(512), nullable=True)

    # Bridge authentication tokens for gateway execution (Phase 3.1)
    bridge_auth_token = Column(String(255), nullable=True)
    bridge_auth_token_prev = Column(String(255), nullable=True)
    bridge_auth_token_prev_expires_at = Column(DateTime, nullable=True)

    # Identity readiness gate (Phase 3.1)
    # True when AGENT.md, SOUL.md, IDENTITY.md, skills/ are mounted
    identity_ready = Column(Boolean, default=False, nullable=False)

    # Checkpoint hydration status for session state recovery (Phase 3.1)
    hydration_status = Column(
        Enum(
            SandboxHydrationStatus.PENDING,
            SandboxHydrationStatus.IN_PROGRESS,
            SandboxHydrationStatus.COMPLETED,
            SandboxHydrationStatus.DEGRADED,
            SandboxHydrationStatus.FAILED,
            name="sandbox_hydration_status",
        ),
        default=SandboxHydrationStatus.PENDING,
        nullable=False,
    )
    hydration_retry_count = Column(Integer, default=0, nullable=False)
    hydration_last_error = Column(Text, nullable=True)

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


# Phase 3 Models: Persistence and Checkpoint Recovery


class RunSession(Base):
    """Run session metadata for non-guest execution.

    Tracks the lifecycle of a single run from queue through completion.
    Links to workspace for tenant isolation and checkpoint context.
    """

    __tablename__ = "run_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session identification
    run_id = Column(String(255), unique=True, nullable=False, index=True)
    parent_run_id = Column(String(255), nullable=True, index=True)

    # Execution state
    state = Column(
        Enum(
            RunSessionState.QUEUED,
            RunSessionState.RUNNING,
            RunSessionState.PAUSED,
            RunSessionState.COMPLETED,
            RunSessionState.FAILED,
            RunSessionState.CANCELLED,
            name="run_session_state",
        ),
        default=RunSessionState.QUEUED,
        nullable=False,
        index=True,
    )

    # Actor and context
    principal_id = Column(String(255), nullable=True)  # User ID or guest principal
    principal_type = Column(String(50), nullable=True)  # "user" | "guest"

    # Sandbox context (restored or created)
    sandbox_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sandbox_instances.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Checkpoint context for this run
    checkpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace_checkpoints.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Request metadata (stored as JSON)
    request_payload_json = Column(Text, nullable=True)

    # Result metadata
    result_payload_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class RuntimeEvent(Base):
    """Runtime events for run timeline and audit.

    Append-only event log for observability and debugging.
    Events are immutable once written.
    """

    __tablename__ = "runtime_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("run_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event classification
    event_type = Column(
        Enum(
            RuntimeEventType.SESSION_STARTED,
            RuntimeEventType.SESSION_PAUSED,
            RuntimeEventType.SESSION_RESUMED,
            RuntimeEventType.SESSION_COMPLETED,
            RuntimeEventType.SESSION_FAILED,
            RuntimeEventType.SESSION_CANCELLED,
            RuntimeEventType.CHECKPOINT_CREATED,
            RuntimeEventType.CHECKPOINT_RESTORE_STARTED,
            RuntimeEventType.CHECKPOINT_RESTORE_COMPLETED,
            RuntimeEventType.CHECKPOINT_RESTORE_FAILED,
            RuntimeEventType.CHECKPOINT_FALLBACK_USED,
            RuntimeEventType.POLICY_VIOLATION,
            RuntimeEventType.RATE_LIMIT_EXCEEDED,
            name="runtime_event_type",
        ),
        nullable=False,
        index=True,
    )

    # Actor and context
    actor_id = Column(String(255), nullable=True)
    actor_type = Column(String(50), nullable=True)

    # Event payload (structured JSON)
    payload_json = Column(Text, nullable=True)

    # Timing
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Correlation (for distributed tracing)
    correlation_id = Column(String(255), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkspaceCheckpoint(Base):
    """Checkpoint metadata for workspace state persistence.

    Tracks checkpoint creation, storage location, and validity.
    Supports fallback chain for restore resilience.
    """

    __tablename__ = "workspace_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Checkpoint identification
    checkpoint_id = Column(String(255), unique=True, nullable=False, index=True)
    version = Column(String(50), nullable=False)

    # Storage reference (S3-compatible object key)
    storage_key = Column(String(512), nullable=False)
    storage_size_bytes = Column(Integer, nullable=True)

    # Checkpoint state
    state = Column(
        Enum(
            CheckpointState.PENDING,
            CheckpointState.IN_PROGRESS,
            CheckpointState.COMPLETED,
            CheckpointState.FAILED,
            CheckpointState.PARTIAL,
            name="checkpoint_state",
        ),
        default=CheckpointState.PENDING,
        nullable=False,
        index=True,
    )

    # Manifest describing checkpoint contents
    manifest_json = Column(Text, nullable=True)

    # Optional: Link to the run that created this checkpoint
    created_by_run_id = Column(String(255), nullable=True, index=True)

    # Fallback chain for resilience
    previous_checkpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace_checkpoints.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class WorkspaceActiveCheckpoint(Base):
    """Active checkpoint pointer per workspace.

    Singleton record per workspace pointing to the currently
    active checkpoint for restore operations.
    """

    __tablename__ = "workspace_active_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Active checkpoint reference
    checkpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace_checkpoints.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Metadata for pointer change audit
    changed_by = Column(String(255), nullable=True)
    changed_reason = Column(Text, nullable=True)

    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AuditEvent(Base):
    """Immutable audit event log.

    Security-relevant events with append-only enforcement.
    Updates and deletes are rejected at the database level.
    """

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Event classification
    category = Column(
        Enum(
            AuditEventCategory.RUN_EXECUTION,
            AuditEventCategory.CHECKPOINT_MANAGEMENT,
            AuditEventCategory.POLICY_ENFORCEMENT,
            AuditEventCategory.SYSTEM_OPERATION,
            name="audit_event_category",
        ),
        nullable=False,
        index=True,
    )

    # Actor identification
    actor_id = Column(String(255), nullable=True, index=True)
    actor_type = Column(String(50), nullable=True)

    # Resource identification
    resource_type = Column(String(100), nullable=False)  # "workspace", "run", "checkpoint"
    resource_id = Column(String(255), nullable=False, index=True)

    # Action and outcome
    action = Column(String(100), nullable=False)
    outcome = Column(String(50), nullable=False)  # "success", "failure", "denied"

    # Detailed payload
    payload_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)

    # Workspace context for tenant isolation
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Timing
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Immutability marker (set once, never changed)
    immutable = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
