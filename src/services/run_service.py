"""Run execution service with guest persistence guard and policy hooks.

Provides run execution with:
- Guest/non-guest persistence guards
- Runtime policy enforcement before network/tool/secret actions
- Scoped secret injection based on policy
"""

from typing import Optional, Dict, Any
from uuid import uuid4, UUID
from dataclasses import dataclass

from src.guest.identity import GuestPrincipal, is_guest_principal
from src.runtime_policy.enforcer import RuntimeEnforcer, PolicyViolationError
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope


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


class RunService:
    """Service for run execution with policy enforcement.

    This service handles the core run execution flow including:
    - Guest mode detection and persistence guards
    - Runtime policy enforcement
    - Scoped secret injection
    """

    def __init__(self, enforcer: Optional[RuntimeEnforcer] = None):
        """Initialize the run service.

        Args:
            enforcer: Runtime enforcer for policy checks
        """
        self.enforcer = enforcer or RuntimeEnforcer()

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


# Type alias for any principal
from typing import Union
from src.identity.key_material import Principal as AuthPrincipal

AnyPrincipal = Union[AuthPrincipal, GuestPrincipal]
