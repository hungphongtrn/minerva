"""Run execution service with guest persistence guard and policy hooks.

Provides run execution with:
- Workspace lifecycle integration for routing
- Picoclaw bridge execution for in-sandbox runtime invocation
- Guest/non-guest persistence guards
- Runtime policy enforcement before network/tool/secret actions
- Scoped secret injection based on policy
"""

from typing import Optional, Dict, Any
from uuid import uuid4, UUID
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.guest.identity import GuestPrincipal, is_guest_principal
from src.runtime_policy.enforcer import RuntimeEnforcer, PolicyViolationError
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope
from src.services.workspace_lifecycle_service import (
    WorkspaceLifecycleService,
    LifecycleTarget,
)
from src.services.picoclaw_bridge_service import (
    PicoclawBridgeService,
    BridgeResult,
    BridgeError,
    BridgeErrorType,
    BridgeTokenBundle,
)
from src.services.runtime_persistence_service import (
    RuntimePersistenceService,
    GuestPersistenceError,
)
from src.services.checkpoint_restore_service import (
    CheckpointRestoreService,
)


@dataclass
class RunContext:
    """Context for a run execution."""

    run_id: str
    principal: Any
    is_guest: bool
    workspace_id: Optional[str]


@dataclass
class RunResult:
    """Result of a run execution."""

    run_id: str
    status: str
    error: Optional[str] = None
    outputs: Optional[Dict[str, Any]] = None


class RoutingErrorType:
    """Error type constants for routing failures.

        Provides deterministic error categorization for API consumers
    to handle different routing failure scenarios programmatically.
    """

    # Pack-specific errors (4xx range)
    PACK_NOT_FOUND = "pack_not_found"
    PACK_WORKSPACE_MISMATCH = "pack_workspace_mismatch"
    PACK_INVALID = "pack_invalid"
    PACK_STALE = "pack_stale"

    # Lease/Concurrency errors (409)
    LEASE_CONFLICT = "lease_conflict"

    # Infrastructure errors (5xx range)
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    SANDBOX_PROVISION_FAILED = "sandbox_provision_failed"
    WORKSPACE_RESOLUTION_FAILED = "workspace_resolution_failed"
    ROUTING_FAILED = "routing_failed"

    # Bridge execution errors (5xx range)
    BRIDGE_HEALTH_CHECK_FAILED = "bridge_health_check_failed"
    BRIDGE_AUTH_FAILED = "bridge_auth_failed"
    BRIDGE_TIMEOUT = "bridge_timeout"
    BRIDGE_TRANSPORT_ERROR = "bridge_transport_error"
    BRIDGE_UPSTREAM_ERROR = "bridge_upstream_error"
    BRIDGE_MALFORMED_RESPONSE = "bridge_malformed_response"


@dataclass
class RunRoutingResult:
    """Result of resolving routing target for a run.

    Contains workspace, sandbox, and lease information for execution.
    """

    success: bool
    workspace_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    sandbox_state: Optional[str] = None
    sandbox_health: Optional[str] = None
    sandbox_url: Optional[str] = None
    agent_pack_id: Optional[str] = None
    lease_acquired: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None
    lifecycle_target: Optional[LifecycleTarget] = None
    # Restore-aware fields
    restore_in_progress: bool = False
    restore_checkpoint_id: Optional[str] = None
    queued: bool = False  # True if run is queued due to restore


class RunService:
    """Service for run execution with policy enforcement.

    This service handles the core run execution flow including:
    - Workspace lifecycle resolution for sandbox routing
    - Guest mode detection and persistence guards
    - Runtime policy enforcement
    - Scoped secret injection
    """

    def __init__(
        self,
        enforcer: Optional[RuntimeEnforcer] = None,
        lifecycle_service: Optional[WorkspaceLifecycleService] = None,
        persistence_service: Optional[RuntimePersistenceService] = None,
        restore_service: Optional[CheckpointRestoreService] = None,
    ):
        """Initialize the run service.

        Args:
            enforcer: Runtime enforcer for policy checks
            lifecycle_service: Workspace lifecycle service for routing
            persistence_service: Optional runtime persistence service for durable runs
            restore_service: Optional checkpoint restore service for cold-start restore
        """
        self.enforcer = enforcer or RuntimeEnforcer()
        self._lifecycle_service = lifecycle_service
        self._persistence_service = persistence_service
        self._restore_service = restore_service

    def start_run(
        self,
        principal: Any,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: Dict[str, Any],
    ) -> RunContext:
        """Start a new run with policy context.

        Args:
            principal: The requesting principal (authenticated or guest)
            egress_policy: Egress policy for this run
            tool_policy: Tool policy for this run
            secret_policy: Secret scope policy for this run
            secrets: Available secrets (will be filtered by policy)

        Returns:
            RunContext with run ID and metadata
        """
        # Generate run ID
        run_id = str(uuid4())

        # Check if guest
        guest = is_guest_principal(principal)

        # Extract workspace ID (None for guests)
        workspace_id = getattr(principal, "workspace_id", None)

        return RunContext(
            run_id=run_id,
            principal=principal,
            is_guest=guest,
            workspace_id=workspace_id,
        )

    def persist_run(self, context: RunContext) -> None:
        """Persist run record - blocked for guests.

        Args:
            context: The run context

        Raises:
            PermissionError: If attempting to persist a guest run
        """
        if context.is_guest:
            raise PermissionError(
                "Guest-mode runs cannot be persisted. "
                "Authenticate with an API key to enable persistence."
            )

        # In real implementation, this would save to database
        # For now, this acts as a guard
        pass

    def persist_checkpoint(
        self, context: RunContext, checkpoint_data: Dict[str, Any]
    ) -> None:
        """Persist checkpoint record - blocked for guests.

        Args:
            context: The run context
            checkpoint_data: Checkpoint data to persist

        Raises:
            PermissionError: If attempting to persist a guest checkpoint
        """
        if context.is_guest:
            raise PermissionError(
                "Guest-mode runs cannot create persistent checkpoints. "
                "Authenticate with an API key to enable checkpoint persistence."
            )

        # In real implementation, this would save to database
        pass

    def authorize_egress(
        self, context: RunContext, url: str, policy: EgressPolicy
    ) -> None:
        """Authorize egress for this run.

        Args:
            context: The run context
            url: The URL to access
            policy: Egress policy to enforce

        Raises:
            PolicyViolationError: If egress is denied
        """
        self.enforcer.authorize_egress(url, policy)

    def authorize_tool(
        self, context: RunContext, tool_id: str, policy: ToolPolicy
    ) -> None:
        """Authorize tool execution for this run.

        Args:
            context: The run context
            tool_id: The tool to execute
            policy: Tool policy to enforce

        Raises:
            PolicyViolationError: If tool access is denied
        """
        self.enforcer.authorize_tool(tool_id, policy)

    def authorize_secret(
        self, context: RunContext, secret_name: str, allowed_secrets: list[str]
    ) -> None:
        """Authorize secret access for this run.

        Args:
            context: The run context
            secret_name: The secret to access
            allowed_secrets: List of allowed secret names

        Raises:
            PolicyViolationError: If secret access is denied
        """
        self.enforcer.authorize_secret(secret_name, allowed_secrets)

    def get_injected_secrets(
        self, context: RunContext, all_secrets: Dict[str, Any], policy: SecretScope
    ) -> Dict[str, Any]:
        """Get secrets filtered by policy for injection.

        Args:
            context: The run context
            all_secrets: All available secrets
            policy: Secret scope policy

        Returns:
            Dictionary of secrets allowed by policy
        """
        return self.enforcer.get_allowed_secrets(all_secrets, policy)

    def execute_run(
        self,
        context: RunContext,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: Dict[str, Any],
        requested_egress_urls: Optional[list[str]] = None,
        requested_tools: Optional[list[str]] = None,
    ) -> RunResult:
        """Execute a run with full policy enforcement.

        This is a placeholder for the full execution flow.
        Real implementation would integrate with agent execution.

        Args:
            context: The run context
            egress_policy: Egress policy
            tool_policy: Tool policy
            secret_policy: Secret scope policy
            secrets: Available secrets
            requested_egress_urls: Egress URLs the run will access
            requested_tools: Tools the run will invoke

        Returns:
            RunResult with execution outcome
        """
        requested_egress_urls = requested_egress_urls or []
        requested_tools = requested_tools or []

        try:
            # Enforce egress policy for all requested URLs
            for url in requested_egress_urls:
                self.authorize_egress(context, url, egress_policy)

            # Enforce tool policy for all requested tools
            for tool_id in requested_tools:
                self.authorize_tool(context, tool_id, tool_policy)

            # Filter secrets to only allowed ones
            injected_secrets = self.get_injected_secrets(
                context, secrets, secret_policy
            )

            # For guest runs, we don't persist
            if not context.is_guest:
                # Persist run record
                self.persist_run(context)

            return RunResult(
                run_id=context.run_id,
                status="success",
                outputs={"secrets_injected": list(injected_secrets.keys())},
            )

        except PolicyViolationError as e:
            return RunResult(
                run_id=context.run_id,
                status="denied",
                error=f"Policy violation ({e.action}): {e.resource} - {e.reason}",
            )
        except PermissionError as e:
            return RunResult(run_id=context.run_id, status="error", error=str(e))
        except Exception as e:
            return RunResult(
                run_id=context.run_id,
                status="error",
                error=f"Execution failed: {str(e)}",
            )

    async def resolve_routing_target(
        self,
        principal: Any,
        session: Session,
        auto_create_workspace: bool = True,
        agent_pack_id: Optional[str] = None,
    ) -> RunRoutingResult:
        """Resolve workspace and sandbox routing target for a run.

        This method integrates with the workspace lifecycle service to:
        1. Ensure durable workspace exists (for authenticated users)
        2. Acquire write lease for same-workspace serialization
        3. Resolve healthy active sandbox or trigger provisioning
        4. Return complete routing information

        For guest principals, this returns an ephemeral routing target
        without workspace persistence.

        Args:
            principal: The requesting principal (authenticated or guest)
            session: Database session for workspace/sandbox operations
            auto_create_workspace: If True, create workspace if not exists
            agent_pack_id: Optional agent pack ID to bind to the sandbox

        Returns:
            RunRoutingResult with routing target information
        """
        run_id = str(uuid4())

        # For guest principals, skip workspace resolution entirely
        if is_guest_principal(principal):
            return RunRoutingResult(
                success=True,
                workspace_id=None,
                sandbox_id=None,
                sandbox_state="guest",
                sandbox_health="healthy",
                lease_acquired=False,
                error=None,
            )

        try:
            # Initialize lifecycle service
            lifecycle = self._lifecycle_service or WorkspaceLifecycleService(
                session=session
            )

            # Check for restore in progress before resolving target
            # This prevents duplicate cold-start restores
            restore_in_progress = False
            restore_checkpoint_id = None
            try:
                restore_in_progress = lifecycle.is_restore_in_progress(
                    target_workspace_id=None
                )  # Will get from target
                if restore_in_progress:
                    restore_checkpoint_id = lifecycle.get_restore_checkpoint_id(
                        target_workspace_id=None
                    )
            except Exception:
                # If restore check fails, continue normally
                pass

            # Resolve target through lifecycle service
            target = await lifecycle.resolve_target(
                principal=principal,
                auto_create=auto_create_workspace,
                acquire_lease=True,
                run_id=run_id,
                agent_pack_id=agent_pack_id,
            )

            # Update restore check now that we have workspace
            if target.workspace:
                try:
                    restore_in_progress = lifecycle.is_restore_in_progress(
                        target.workspace.id
                    )
                    if restore_in_progress:
                        restore_checkpoint_id = lifecycle.get_restore_checkpoint_id(
                            target.workspace.id
                        )
                        # Return queued status - restore in progress
                        return RunRoutingResult(
                            success=True,  # Not a failure, just queued
                            workspace_id=str(target.workspace.id),
                            sandbox_id=None,
                            sandbox_state="restoring",
                            sandbox_health="unknown",
                            lease_acquired=False,
                            error=None,
                            restore_in_progress=True,
                            restore_checkpoint_id=restore_checkpoint_id,
                            queued=True,
                            lifecycle_target=target,
                        )
                except Exception:
                    pass

            # Fail-fast: workspace must exist for non-guest runs
            if not target.workspace:
                return RunRoutingResult(
                    success=False,
                    error_type=RoutingErrorType.WORKSPACE_RESOLUTION_FAILED,
                    error=f"Workspace resolution failed: {target.error or 'No workspace found'}",
                )

            # Fail-fast: routing result must be successful
            if not target.routing_result or not target.routing_result.success:
                error_msg = target.error or (
                    target.routing_result.message
                    if target.routing_result
                    else "Routing failed: no healthy sandbox available"
                )
                error_type = self._categorize_routing_error(error_msg)
                return RunRoutingResult(
                    success=False,
                    workspace_id=str(target.workspace.id),
                    error_type=error_type,
                    error=error_msg,
                    lease_acquired=target.lease_acquired,
                    lifecycle_target=target,
                )

            # Fail-fast: sandbox must exist for successful routing
            routing_result = target.routing_result
            if not routing_result.sandbox:
                error_type = self._categorize_routing_error(
                    routing_result.message or ""
                )
                return RunRoutingResult(
                    success=False,
                    workspace_id=str(target.workspace.id),
                    error_type=error_type,
                    error=routing_result.message
                    or "Routing failed: no sandbox provisioned",
                    lease_acquired=target.lease_acquired,
                    lifecycle_target=target,
                )

            # Extract sandbox info from successful routing
            sandbox_id = str(routing_result.sandbox.id)
            sandbox_state = None
            sandbox_health = None

            if hasattr(routing_result.sandbox, "state"):
                state_val = routing_result.sandbox.state
                # Handle both enum (PostgreSQL) and string (SQLite) types
                if hasattr(state_val, "value"):
                    sandbox_state = str(state_val.value)
                else:
                    sandbox_state = str(state_val)
            if hasattr(routing_result.sandbox, "health_status"):
                health = routing_result.sandbox.health_status
                if health:
                    # Handle both enum (PostgreSQL) and string (SQLite) types
                    if hasattr(health, "value"):
                        sandbox_health = str(health.value)
                    else:
                        sandbox_health = str(health)

            # Handle RESTORING state - return queued status
            if sandbox_state == "restoring":
                return RunRoutingResult(
                    success=True,  # Not a failure, just queued
                    workspace_id=str(target.workspace.id),
                    sandbox_id=sandbox_id,
                    sandbox_state=sandbox_state,
                    sandbox_health=sandbox_health,
                    lease_acquired=target.lease_acquired,
                    error=None,
                    restore_in_progress=True,
                    queued=True,
                    lifecycle_target=target,
                )

            # Get sandbox URL and agent_pack_id from the sandbox instance
            sandbox_url = None
            agent_pack_id_str = None
            if routing_result.sandbox:
                if hasattr(routing_result.sandbox, "gateway_url"):
                    sandbox_url = routing_result.sandbox.gateway_url
                if (
                    hasattr(routing_result.sandbox, "agent_pack_id")
                    and routing_result.sandbox.agent_pack_id
                ):
                    agent_pack_id_str = str(routing_result.sandbox.agent_pack_id)

            return RunRoutingResult(
                success=True,
                workspace_id=str(target.workspace.id),
                sandbox_id=sandbox_id,
                sandbox_state=sandbox_state or "unknown",
                sandbox_health=sandbox_health,
                sandbox_url=sandbox_url,
                agent_pack_id=agent_pack_id_str,
                lease_acquired=target.lease_acquired,
                error=None,
                error_type=None,
                lifecycle_target=target,
            )

        except Exception as e:
            return RunRoutingResult(
                success=False,
                error_type=RoutingErrorType.ROUTING_FAILED,
                error=f"Routing resolution failed: {str(e)}",
            )

    async def execute_with_routing(
        self,
        principal: Any,
        session: Session,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: Dict[str, Any],
        requested_egress_urls: Optional[list[str]] = None,
        requested_tools: Optional[list[str]] = None,
        agent_pack_id: Optional[str] = None,
        input_message: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RunResult:
        """Execute a run with full routing and policy enforcement.

        This is the main entrypoint for run execution that:
        1. Resolves workspace and sandbox routing target
        2. Enforces runtime policies
        3. Persists run session and events (non-guest only)
        4. Executes the run via Picoclaw bridge (if sandbox available)
        5. Updates persistence with results
        6. Releases lease deterministically

        Args:
            principal: The requesting principal
            session: Database session
            egress_policy: Egress policy
            tool_policy: Tool policy
            secret_policy: Secret scope policy
            secrets: Available secrets
            requested_egress_urls: Egress URLs the run will access
            requested_tools: Tools the run will invoke
            agent_pack_id: Optional agent pack to bind to the run
            input_message: The input message for bridge execution
            session_id: Optional session ID for session continuity
                       (same user + same session = same Picoclaw session)

        Returns:
            RunResult with execution outcome
        """
        # Initialize persistence service if not provided
        persistence = self._persistence_service or RuntimePersistenceService(session)

        # Resolve routing target first, passing agent_pack_id for pack binding
        routing = await self.resolve_routing_target(
            principal, session, agent_pack_id=agent_pack_id
        )

        if not routing.success:
            result = RunResult(
                run_id=str(uuid4()),
                status="error",
                error=routing.error or "Failed to resolve routing target",
            )
            # Include routing error type for API error mapping
            result.outputs = {"routing_error_type": routing.error_type}
            return result

        # Start the run
        context = self.start_run(
            principal=principal,
            egress_policy=egress_policy,
            tool_policy=tool_policy,
            secret_policy=secret_policy,
            secrets=secrets,
        )

        # Update context with workspace from routing
        if routing.workspace_id:
            context.workspace_id = routing.workspace_id

        # Create run session for non-guest runs
        run_session_id: Optional[UUID] = None
        if not context.is_guest and routing.workspace_id and routing.sandbox_id:
            try:
                # Parse UUIDs from routing result
                workspace_uuid = UUID(routing.workspace_id)
                sandbox_uuid = UUID(routing.sandbox_id)

                # Get principal ID from context
                principal_id = self._get_principal_id(principal)
                principal_type = "user" if not context.is_guest else "guest"

                run_session_id = persistence.create_run_session(
                    workspace_id=workspace_uuid,
                    run_id=context.run_id,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    is_guest=context.is_guest,
                    request_payload={
                        "input": input_message,
                        "egress_urls": requested_egress_urls,
                        "tools": requested_tools,
                    },
                    sandbox_id=sandbox_uuid,
                )
            except GuestPersistenceError:
                # Expected for guests - no persistence
                pass
            except Exception:
                # Log but don't fail the run if persistence fails
                # (could be a DB error, but run should continue)
                pass

        # Execute with policy enforcement
        result = self.execute_run(
            context=context,
            egress_policy=egress_policy,
            tool_policy=tool_policy,
            secret_policy=secret_policy,
            secrets=secrets,
            requested_egress_urls=requested_egress_urls or [],
            requested_tools=requested_tools or [],
        )

        # Add routing info to outputs
        if result.outputs is None:
            result.outputs = {}

        result.outputs["routing"] = {
            "workspace_id": routing.workspace_id,
            "sandbox_id": routing.sandbox_id,
            "sandbox_state": routing.sandbox_state,
            "sandbox_health": routing.sandbox_health,
            "lease_acquired": routing.lease_acquired,
        }

        # If we have a sandbox and input message, execute via Picoclaw bridge
        bridge_error = None
        if routing.sandbox_id and input_message:
            # Determine sender_id: guest uses "guest", otherwise use external_user_id
            sender_id = (
                "guest"
                if context.is_guest
                else getattr(principal, "external_user_id", None)
            )
            bridge_result = await self._execute_via_bridge(
                routing=routing,
                message=input_message,
                is_guest=context.is_guest,
                session=session,
                session_id=session_id,
                sender_id=sender_id,
            )

            # Update result with bridge execution output
            if bridge_result.success:
                result.outputs["bridge"] = {
                    "success": True,
                    "output": bridge_result.output,
                }
                # Include final assistant output for API response
                if bridge_result.output:
                    result.outputs["final_output"] = bridge_result.output.get(
                        "message"
                    ) or bridge_result.output.get("content")
            else:
                # Bridge execution failed - update status and include error
                result.status = "error"
                bridge_error = (
                    bridge_result.error.message
                    if bridge_result.error
                    else "Bridge execution failed"
                )
                result.error = bridge_error
                result.outputs["routing_error_type"] = self._map_bridge_error_type(
                    bridge_result.error
                )
                result.outputs["bridge"] = {
                    "success": False,
                    "error": bridge_result.error.to_dict()
                    if bridge_result.error
                    else None,
                }

        # Update run session state based on result (non-guest only)
        if run_session_id and not context.is_guest:
            try:
                principal_id = self._get_principal_id(principal)
                workspace_uuid = (
                    UUID(routing.workspace_id) if routing.workspace_id else None
                )

                if result.status == "success":
                    persistence.mark_run_completed(
                        run_session_id=run_session_id,
                        workspace_id=workspace_uuid,
                        run_id=context.run_id,
                        result_payload=result.outputs,
                        principal_id=principal_id,
                        is_guest=context.is_guest,
                    )
                else:
                    error_msg = result.error or "Run failed"
                    persistence.mark_run_failed(
                        run_session_id=run_session_id,
                        workspace_id=workspace_uuid,
                        run_id=context.run_id,
                        error_message=error_msg,
                        error_code=result.outputs.get("routing_error_type")
                        if result.outputs
                        else None,
                        principal_id=principal_id,
                        is_guest=context.is_guest,
                    )
            except Exception:
                # Persistence failure shouldn't fail the run
                pass

        # Release lease deterministically
        if routing.lease_acquired and routing.workspace_id:
            try:
                from src.db.repositories.workspace_lease_repository import (
                    WorkspaceLeaseRepository,
                )

                lease_repo = WorkspaceLeaseRepository(session)
                lease_repo.release_lease(
                    workspace_id=UUID(routing.workspace_id),
                    holder_run_id=context.run_id,
                )
            except Exception:
                # Lease release failure shouldn't fail the run
                pass

        return result

    def _get_principal_id(self, principal: Any) -> Optional[str]:
        """Extract principal ID from principal object.

        Args:
            principal: The principal object (User, GuestPrincipal, etc.)

        Returns:
            Principal ID string or None.
        """
        if hasattr(principal, "user_id"):
            return str(principal.user_id)
        if hasattr(principal, "id"):
            return str(principal.id)
        if hasattr(principal, "principal_id"):
            return str(principal.principal_id)
        return None

    def _generate_session_key(
        self,
        workspace_id: Optional[str],
        agent_pack_id: Optional[str],
        run_id: str,
        is_guest: bool,
        session_id: Optional[str] = None,
    ) -> str:
        """Generate deterministic session key scoped to workspace+pack.

        For authenticated runs: session is scoped to workspace + agent_pack
                         If session_id provided, uses minerva:{workspace_id}:{pack_scope}:{session_id}
        For guest runs: each request gets ephemeral unique session (no continuity)

        Args:
            workspace_id: The workspace ID
            agent_pack_id: The agent pack ID (may be None)
            run_id: The run ID
            is_guest: Whether this is a guest request
            session_id: Optional session ID for continuity

        Returns:
            Session key string
        """
        if is_guest:
            # Guest sessions are ephemeral - no continuity across requests
            return f"minerva:guest:{run_id}"

        # Authenticated sessions are scoped to workspace + pack
        pack_scope = agent_pack_id or "default"
        # Use session_id if provided for continuity, otherwise use run_id
        continuity_key = session_id if session_id else run_id
        return f"minerva:{workspace_id}:{pack_scope}:{continuity_key}"

    async def _execute_via_bridge(
        self,
        routing: RunRoutingResult,
        message: str,
        is_guest: bool,
        session: Session,
        session_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> BridgeResult:
        """Execute request via Picoclaw bridge with bounded recovery.

        This method implements:
        1. Sandbox-scoped token resolution from repository
        2. Authoritative gateway URL enforcement (no synthetic URLs)
        3. Bounded recovery loop (max 3 attempts) for transient failures
        4. Deterministic fail-fast on recovery exhaustion

        Args:
            routing: The routing result containing sandbox info
            message: The input message for execution
            is_guest: Whether this is a guest request
            session: Database session for token resolution and recovery
            session_id: Optional session ID for continuity
            sender_id: External user identifier for Picoclaw conversation scoping

        Returns:
            BridgeResult with execution outcome
        """
        # Generate session key scoped to workspace+pack with optional session continuity
        session_key = self._generate_session_key(
            workspace_id=routing.workspace_id,
            agent_pack_id=routing.lifecycle_target.agent_pack_id
            if routing.lifecycle_target
            else None,
            run_id=str(uuid4()),
            is_guest=is_guest,
            session_id=session_id,
        )

        # Bounded recovery: max 3 attempts
        MAX_RECOVERY_ATTEMPTS = 3
        last_error = None

        for attempt in range(MAX_RECOVERY_ATTEMPTS):
            # Get authoritative sandbox URL
            sandbox_url = self._get_authoritative_sandbox_url(routing)

            if not sandbox_url:
                return BridgeResult(
                    success=False,
                    error=BridgeError(
                        error_type=BridgeErrorType.TRANSPORT_ERROR,
                        message="Sandbox gateway URL not available: authoritative endpoint required",
                        remediation="Sandbox may not be fully provisioned or gateway_url is missing. Reprovision may be needed.",
                    ),
                )

            # Resolve bridge tokens from sandbox metadata
            token_bundle = self._resolve_bridge_tokens(routing, session)

            if not token_bundle or not token_bundle.current:
                return BridgeResult(
                    success=False,
                    error=BridgeError(
                        error_type=BridgeErrorType.AUTH_FAILED,
                        message="Bridge authentication failed: no valid token resolved from sandbox metadata",
                        remediation="Token must be set during sandbox provisioning. Check sandbox configuration.",
                    ),
                )

            # Execute via bridge
            bridge_service = PicoclawBridgeService()

            result = await bridge_service.execute(
                sandbox_url=sandbox_url,
                message=message,
                session_key=session_key,
                token_bundle=token_bundle,
                workspace_id=routing.workspace_id,
                agent_pack_id=routing.lifecycle_target.agent_pack_id
                if routing.lifecycle_target
                else None,
                run_id=session_key.split(":")[-1],
                sender_id=sender_id,
                session_id=session_id,
            )

            if result.success:
                return result

            # Check if error is recoverable
            if not self._is_recoverable_bridge_error(result.error):
                # Non-recoverable error: fail fast
                return result

            # Recoverable error: store and retry if attempts remain
            last_error = result.error

            if attempt < MAX_RECOVERY_ATTEMPTS - 1:
                # Force reprovision through lifecycle resolution
                try:
                    routing = await self._recover_routing_target(routing, session)
                    if not routing or not routing.success:
                        # Recovery failed - return last error
                        return BridgeResult(
                            success=False,
                            error=BridgeError(
                                error_type=BridgeErrorType.TRANSPORT_ERROR,
                                message=f"Bridge execution failed after {attempt + 1} attempts. Recovery reprovisioning failed.",
                                remediation="Sandbox infrastructure may be unavailable. Retry or contact support.",
                            ),
                        )
                except Exception as e:
                    # Recovery threw exception - fail fast
                    return BridgeResult(
                        success=False,
                        error=BridgeError(
                            error_type=BridgeErrorType.TRANSPORT_ERROR,
                            message=f"Bridge execution failed after {attempt + 1} attempts. Recovery error: {str(e)}",
                            remediation="Check provider status and retry.",
                        ),
                    )

        # Exhausted all recovery attempts
        return BridgeResult(
            success=False,
            error=BridgeError(
                error_type=BridgeErrorType.TRANSPORT_ERROR,
                message=f"Bridge execution failed after {MAX_RECOVERY_ATTEMPTS} recovery attempts. Last error: {last_error.message if last_error else 'Unknown'}",
                remediation="Sandbox endpoint remains unavailable after reprovisioning attempts. Check provider infrastructure or contact support.",
            ),
        )

    def _get_authoritative_sandbox_url(
        self, routing: RunRoutingResult
    ) -> Optional[str]:
        """Get the authoritative sandbox gateway URL from routing result.

        This method enforces that only explicitly provisioned gateway URLs
        are used. No synthetic or constructed URLs are permitted.

        Args:
            routing: The routing result

        Returns:
            Sandbox URL string from authoritative source, or None if not available
        """
        # First try the direct URL field from routing result
        if routing.sandbox_url:
            return routing.sandbox_url

        # Fallback: try to get URL from lifecycle target's sandbox
        if routing.lifecycle_target and routing.lifecycle_target.routing_result:
            sandbox = routing.lifecycle_target.routing_result.sandbox
            if sandbox and hasattr(sandbox, "gateway_url") and sandbox.gateway_url:
                return sandbox.gateway_url

        # No synthetic URL construction allowed - return None for fail-closed
        return None

    def _resolve_bridge_tokens(
        self, routing: RunRoutingResult, session: Session
    ) -> Optional[BridgeTokenBundle]:
        """Resolve bridge authentication tokens from sandbox metadata.

        Uses the sandbox instance repository to get the current and
        grace-period tokens for the sandbox.

        Args:
            routing: The routing result containing sandbox ID
            session: Database session

        Returns:
            BridgeTokenBundle with current and optional grace token, or None
        """
        if not routing.sandbox_id:
            return None

        try:
            from src.db.repositories.sandbox_instance_repository import (
                SandboxInstanceRepository,
            )

            repo = SandboxInstanceRepository(session)

            # Parse sandbox ID
            sandbox_uuid = UUID(routing.sandbox_id)

            # Resolve tokens from repository
            token_data = repo.resolve_bridge_tokens(sandbox_uuid)

            if not token_data or not token_data.get("current"):
                return None

            # Build token bundle
            return BridgeTokenBundle(
                current=token_data["current"],
                previous=token_data.get("previous"),
                previous_expires_at=token_data.get("previous_expires_at"),
            )

        except Exception:
            # Fail-closed: any resolution failure returns None
            return None

    def _is_recoverable_bridge_error(self, error: Optional[BridgeError]) -> bool:
        """Check if a bridge error is recoverable via reprovisioning.

        Args:
            error: The bridge error to check

        Returns:
            True if error may be resolved by reprovisioning
        """
        if not error:
            return False

        # These errors may be resolved by fresh reprovisioning
        recoverable_types = {
            BridgeErrorType.HEALTH_CHECK_FAILED,
            BridgeErrorType.TIMEOUT,
            BridgeErrorType.TRANSPORT_ERROR,
        }

        return error.error_type in recoverable_types

    async def _recover_routing_target(
        self, current_routing: RunRoutingResult, session: Session
    ) -> RunRoutingResult:
        """Attempt to recover routing by forcing reprovision.

        This forces a fresh lifecycle resolution which may provision
        a new sandbox if the current one is unhealthy.

        Args:
            current_routing: The current failed routing result
            session: Database session

        Returns:
            New RunRoutingResult after recovery attempt
        """
        if not current_routing.workspace_id:
            return RunRoutingResult(
                success=False,
                error="Cannot recover: no workspace ID available",
            )

        # Force fresh lifecycle resolution
        lifecycle = self._lifecycle_service or WorkspaceLifecycleService(
            session=session
        )

        # Get principal from routing context if available
        principal = None
        if current_routing.lifecycle_target:
            principal = getattr(current_routing.lifecycle_target, "principal", None)

        if not principal:
            # Cannot recover without principal
            return RunRoutingResult(
                success=False,
                error="Cannot recover: principal context lost",
            )

        # Re-resolve with forced fresh target
        target = await lifecycle.resolve_target(
            principal=principal,
            auto_create=False,  # Don't create new workspace
            acquire_lease=True,
            run_id=str(uuid4()),
            agent_pack_id=current_routing.agent_pack_id,
        )

        # Convert to RunRoutingResult format
        if not target.success or not target.routing_result:
            return RunRoutingResult(
                success=False,
                error=target.error or "Recovery routing failed",
                workspace_id=current_routing.workspace_id,
            )

        # Extract sandbox info
        routing_result = target.routing_result
        if not routing_result.sandbox:
            return RunRoutingResult(
                success=False,
                error="Recovery failed: no sandbox provisioned",
                workspace_id=current_routing.workspace_id,
            )

        # Build fresh routing result
        sandbox_id = str(routing_result.sandbox.id)
        sandbox_state = None
        sandbox_health = None
        sandbox_url = None

        if hasattr(routing_result.sandbox, "state"):
            state_val = routing_result.sandbox.state
            sandbox_state = str(
                state_val.value if hasattr(state_val, "value") else state_val
            )
        if hasattr(routing_result.sandbox, "health_status"):
            health = routing_result.sandbox.health_status
            if health:
                sandbox_health = str(
                    health.value if hasattr(health, "value") else health
                )
        if hasattr(routing_result.sandbox, "gateway_url"):
            sandbox_url = routing_result.sandbox.gateway_url

        return RunRoutingResult(
            success=True,
            workspace_id=current_routing.workspace_id,
            sandbox_id=sandbox_id,
            sandbox_state=sandbox_state or "unknown",
            sandbox_health=sandbox_health,
            sandbox_url=sandbox_url,
            agent_pack_id=current_routing.agent_pack_id,
            lease_acquired=target.lease_acquired,
            lifecycle_target=target,
        )

    def _map_bridge_error_type(self, error: Optional[BridgeError]) -> str:
        """Map bridge error to routing error type for API mapping.

        Args:
            error: The bridge error

        Returns:
            Routing error type constant
        """
        if not error:
            return RoutingErrorType.ROUTING_FAILED

        error_type_map = {
            BridgeErrorType.HEALTH_CHECK_FAILED: RoutingErrorType.BRIDGE_HEALTH_CHECK_FAILED,
            BridgeErrorType.AUTH_FAILED: RoutingErrorType.BRIDGE_AUTH_FAILED,
            BridgeErrorType.TIMEOUT: RoutingErrorType.BRIDGE_TIMEOUT,
            BridgeErrorType.TRANSPORT_ERROR: RoutingErrorType.BRIDGE_TRANSPORT_ERROR,
            BridgeErrorType.UPSTREAM_ERROR: RoutingErrorType.BRIDGE_UPSTREAM_ERROR,
            BridgeErrorType.MALFORMED_RESPONSE: RoutingErrorType.BRIDGE_MALFORMED_RESPONSE,
        }

        return error_type_map.get(error.error_type, RoutingErrorType.ROUTING_FAILED)

    def _categorize_routing_error(self, error_msg: str) -> str:
        """Categorize routing error message into deterministic error type.

        Args:
            error_msg: The error message from routing failure.

        Returns:
            Error type constant from RoutingErrorType.
        """
        if not error_msg:
            return RoutingErrorType.ROUTING_FAILED

        error_lower = error_msg.lower()

        # Pack-specific errors (client errors - 4xx)
        if "agent pack not found" in error_lower:
            return RoutingErrorType.PACK_NOT_FOUND
        if "does not belong to workspace" in error_lower:
            return RoutingErrorType.PACK_WORKSPACE_MISMATCH
        if "is not valid" in error_lower:
            return RoutingErrorType.PACK_INVALID
        if "is not active" in error_lower:
            return RoutingErrorType.PACK_STALE
        if "stale" in error_lower:
            return RoutingErrorType.PACK_STALE

        # Lease/concurrency errors (409)
        if "lease" in error_lower and (
            "conflict" in error_lower or "acquire" in error_lower
        ):
            return RoutingErrorType.LEASE_CONFLICT

        # Provider/infrastructure errors (5xx - must be checked BEFORE workspace_resolution)
        # These are provider/runtime failures, not client errors
        if "provision" in error_lower and "failed" in error_lower:
            return RoutingErrorType.SANDBOX_PROVISION_FAILED
        if "failed to provision" in error_lower:
            return RoutingErrorType.SANDBOX_PROVISION_FAILED
        if (
            "provider unavailable" in error_lower
            or "provider" in error_lower
            and "unavailable" in error_lower
        ):
            return RoutingErrorType.PROVIDER_UNAVAILABLE
        if "daytona" in error_lower and (
            "error" in error_lower or "failed" in error_lower
        ):
            # Daytona provider errors are infrastructure failures
            return RoutingErrorType.SANDBOX_PROVISION_FAILED

        # Workspace resolution errors (400) - checked AFTER infrastructure errors
        # Only match explicit workspace resolution failures, not provider errors
        if (
            "workspace" in error_lower
            and "resolution" in error_lower
            and "not found" in error_lower
        ):
            return RoutingErrorType.WORKSPACE_RESOLUTION_FAILED

        return RoutingErrorType.ROUTING_FAILED


# Type alias for any principal
from typing import Union
from src.identity.key_material import Principal as AuthPrincipal

AnyPrincipal = Union[AuthPrincipal, GuestPrincipal]
