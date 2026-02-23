"""Runtime policy enforcement hooks.

Provides enforcement helpers used by run execution and tool/secret access
callsites to ensure no bypass path exists. All enforcement is default-deny.
"""

from typing import Dict, Any, Optional

from src.runtime_policy.engine import RuntimePolicyEngine
from src.runtime_policy.models import (
    PolicyDecision,
    EgressPolicy,
    ToolPolicy,
    SecretScope,
)


class PolicyViolationError(RuntimeError):
    """Raised when a runtime policy is violated."""

    def __init__(self, action: str, resource: str, reason: str):
        self.action = action
        self.resource = resource
        self.reason = reason
        super().__init__(f"Policy violation ({action}): {resource} - {reason}")


class RuntimeEnforcer:
    """Enforces runtime policies by raising on violations.

    This class provides enforcement hooks that are called before
    egress, tool, and secret access. On policy denial, it raises
    PolicyViolationError which must be caught and handled.
    """

    def __init__(self, engine: Optional[RuntimePolicyEngine] = None):
        """Initialize the enforcer with a policy engine.

        Args:
            engine: Policy engine to use (creates default if None)
        """
        self.engine = engine or RuntimePolicyEngine()

    def authorize_egress(self, url: str, policy: EgressPolicy) -> None:
        """Authorize an egress request, raising on denial.

        Args:
            url: The URL to access
            policy: The egress policy to enforce

        Raises:
            PolicyViolationError: If egress is denied by policy
        """
        decision = self.engine.evaluate_egress_policy(url, policy)

        if not decision.allowed:
            raise PolicyViolationError(
                action="egress", resource=url, reason=decision.reason
            )

    def authorize_tool(self, tool_id: str, policy: ToolPolicy) -> None:
        """Authorize a tool execution, raising on denial.

        Args:
            tool_id: The tool to execute
            policy: The tool policy to enforce

        Raises:
            PolicyViolationError: If tool access is denied by policy
        """
        decision = self.engine.evaluate_tool_policy(tool_id, policy)

        if not decision.allowed:
            raise PolicyViolationError(
                action="tool", resource=tool_id, reason=decision.reason
            )

    def authorize_secret(self, secret_name: str, allowed_secrets: list[str]) -> None:
        """Authorize a secret access, raising on denial.

        Args:
            secret_name: The secret to access
            allowed_secrets: List of allowed secret names

        Raises:
            PolicyViolationError: If secret access is denied by policy
        """
        decision = self.engine.evaluate_secret(secret_name, allowed_secrets)

        if not decision.allowed:
            raise PolicyViolationError(
                action="secret", resource=secret_name, reason=decision.reason
            )

    def get_allowed_secrets(
        self, all_secrets: Dict[str, Any], policy: SecretScope
    ) -> Dict[str, Any]:
        """Filter secrets to only those allowed by policy.

        Args:
            all_secrets: Dictionary of all available secrets
            policy: The secret scope policy

        Returns:
            Dictionary containing only allowed secrets
        """
        allowed = {}

        for secret_name in policy.allowed_secrets:
            if secret_name in all_secrets:
                allowed[secret_name] = all_secrets[secret_name]

        return allowed

    def check_all(
        self,
        egress_url: Optional[str] = None,
        tool_id: Optional[str] = None,
        secret_name: Optional[str] = None,
        egress_policy: Optional[EgressPolicy] = None,
        tool_policy: Optional[ToolPolicy] = None,
        allowed_secrets: Optional[list[str]] = None,
    ) -> list[PolicyDecision]:
        """Check multiple policies at once.

        Args:
            egress_url: URL to check (if any)
            tool_id: Tool to check (if any)
            secret_name: Secret to check (if any)
            egress_policy: Egress policy to apply
            tool_policy: Tool policy to apply
            allowed_secrets: List of allowed secrets

        Returns:
            List of policy decisions (empty list if all allowed)

        Note:
            This method does not raise - use individual authorize_*
            methods for enforcement that raises on denial.
        """
        decisions = []

        if egress_url and egress_policy:
            decision = self.engine.evaluate_egress_policy(egress_url, egress_policy)
            if not decision.allowed:
                decisions.append(decision)

        if tool_id and tool_policy:
            decision = self.engine.evaluate_tool_policy(tool_id, tool_policy)
            if not decision.allowed:
                decisions.append(decision)

        if secret_name and allowed_secrets is not None:
            decision = self.engine.evaluate_secret(secret_name, allowed_secrets)
            if not decision.allowed:
                decisions.append(decision)

        return decisions
