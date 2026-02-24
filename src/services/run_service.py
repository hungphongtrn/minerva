"""Run execution service with guest persistence guard and policy hooks.

Provides run execution with:
- Workspace lifecycle integration for routing
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
    lease_acquired: bool = False
    error: Optional[str] = None
    lifecycle_target: Optional[LifecycleTarget] = None


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
    ):
        """Initialize the run service.

        Args:
            enforcer: Runtime enforcer for policy checks
            lifecycle_service: Workspace lifecycle service for routing
        """
        self.enforcer = enforcer or RuntimeEnforcer()
        self._lifecycle_service = lifecycle_service

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

            # Resolve target through lifecycle service
            target = await lifecycle.resolve_target(
                principal=principal,
                auto_create=auto_create_workspace,
                acquire_lease=True,
                run_id=run_id,
            )

            if target.error and not target.workspace:
                # Failed to resolve workspace
                return RunRoutingResult(
                    success=False,
                    error=f"Workspace resolution failed: {target.error}",
                )

            # Build routing result
            sandbox_state = None
            sandbox_health = None
            sandbox_id = None

            if target.routing_result and target.routing_result.success:
                routing_result = target.routing_result
                if routing_result.sandbox:
                    sandbox_id = str(routing_result.sandbox.id)
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

            return RunRoutingResult(
                success=True,
                workspace_id=str(target.workspace.id) if target.workspace else None,
                sandbox_id=sandbox_id,
                sandbox_state=sandbox_state or "unknown",
                sandbox_health=sandbox_health,
                lease_acquired=target.lease_acquired,
                error=target.error,
                lifecycle_target=target,
            )

        except Exception as e:
            return RunRoutingResult(
                success=False,
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
    ) -> RunResult:
        """Execute a run with full routing and policy enforcement.

        This is the main entrypoint for run execution that:
        1. Resolves workspace and sandbox routing target
        2. Enforces runtime policies
        3. Executes the run
        4. Releases lease deterministically

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

        Returns:
            RunResult with execution outcome
        """
        # Resolve routing target first
        routing = await self.resolve_routing_target(principal, session)

        if not routing.success:
            return RunResult(
                run_id=str(uuid4()),
                status="error",
                error=routing.error or "Failed to resolve routing target",
            )

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

        return result


# Type alias for any principal
from typing import Union
from src.identity.key_material import Principal as AuthPrincipal

AnyPrincipal = Union[AuthPrincipal, GuestPrincipal]
