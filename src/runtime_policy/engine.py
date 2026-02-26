"""Runtime policy evaluation engine.

Provides default-deny policy evaluation for egress, tool, and secret actions.
All decisions default to deny unless explicitly allowed.
"""

from urllib.parse import urlparse

from src.runtime_policy.models import (
    PolicyDecision,
    EgressPolicy,
    ToolPolicy,
)


class RuntimePolicyEngine:
    """Policy evaluation engine implementing default-deny semantics.

    All evaluate_* methods return deny unless the action is explicitly
    allowed by the provided policy.
    """

    def evaluate_egress(self, url: str, allowed_hosts: list[str]) -> PolicyDecision:
        """Evaluate if a URL is allowed for egress.

        Args:
            url: The URL to evaluate
            allowed_hosts: List of allowed hostnames/patterns

        Returns:
            PolicyDecision with allowed=True if URL matches allowlist
        """
        if not allowed_hosts:
            return PolicyDecision(
                allowed=False,
                reason="Egress denied: no hosts allowed by policy (default deny)",
            )

        # Parse URL to extract hostname
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return PolicyDecision(
                    allowed=False, reason=f"Egress denied: invalid URL '{url}'"
                )
        except Exception:
            return PolicyDecision(
                allowed=False, reason=f"Egress denied: could not parse URL '{url}'"
            )

        # Normalize hostname
        hostname = hostname.lower().strip()

        # Check against allowlist
        for allowed in allowed_hosts:
            allowed = allowed.lower().strip()

            # Exact match
            if hostname == allowed:
                return PolicyDecision(
                    allowed=True, reason=f"Egress allowed: '{hostname}' matches policy"
                )

            # Wildcard subdomain match (e.g., *.example.com)
            if allowed.startswith("*."):
                suffix = allowed[2:]  # Remove *.
                if hostname.endswith(suffix) or hostname == suffix:
                    return PolicyDecision(
                        allowed=True,
                        reason=f"Egress allowed: '{hostname}' matches pattern '{allowed}'",
                    )

        return PolicyDecision(
            allowed=False,
            reason=f"Egress denied: '{hostname}' not in allowed hosts list",
        )

    def evaluate_tool(self, tool_id: str, allowed_tools: list[str]) -> PolicyDecision:
        """Evaluate if a tool is allowed for execution.

        Args:
            tool_id: The tool identifier to evaluate
            allowed_tools: List of allowed tool IDs

        Returns:
            PolicyDecision with allowed=True if tool is allowlisted
        """
        if not allowed_tools:
            return PolicyDecision(
                allowed=False,
                reason="Tool access denied: no tools allowed by policy (default deny)",
            )

        # Normalize tool ID
        tool_id = tool_id.lower().strip()
        allowed_normalized = [t.lower().strip() for t in allowed_tools]

        if tool_id in allowed_normalized:
            return PolicyDecision(
                allowed=True,
                reason=f"Tool access allowed: '{tool_id}' is in allowed list",
            )

        return PolicyDecision(
            allowed=False,
            reason=f"Tool access denied: '{tool_id}' not in allowed tools list",
        )

    def evaluate_secret(
        self, secret_name: str, allowed_secrets: list[str]
    ) -> PolicyDecision:
        """Evaluate if a secret can be accessed.

        Args:
            secret_name: The secret name to evaluate
            allowed_secrets: List of allowed secret names

        Returns:
            PolicyDecision with allowed=True if secret is allowlisted
        """
        if not allowed_secrets:
            return PolicyDecision(
                allowed=False,
                reason="Secret access denied: no secrets allowed by policy (default deny)",
            )

        # Normalize secret name (case-sensitive usually, but we'll strip whitespace)
        secret_name = secret_name.strip()
        allowed_normalized = [s.strip() for s in allowed_secrets]

        if secret_name in allowed_normalized:
            return PolicyDecision(
                allowed=True,
                reason=f"Secret access allowed: '{secret_name}' is in allowed list",
            )

        return PolicyDecision(
            allowed=False,
            reason=f"Secret access denied: '{secret_name}' not in allowed secrets list",
        )

    def evaluate_egress_policy(self, url: str, policy: EgressPolicy) -> PolicyDecision:
        """Evaluate egress against an EgressPolicy object.

        Args:
            url: The URL to evaluate
            policy: The egress policy to check against

        Returns:
            PolicyDecision
        """
        return self.evaluate_egress(url, policy.allowed_hosts)

    def evaluate_tool_policy(self, tool_id: str, policy: ToolPolicy) -> PolicyDecision:
        """Evaluate tool against a ToolPolicy object.

        Args:
            tool_id: The tool ID to evaluate
            policy: The tool policy to check against

        Returns:
            PolicyDecision
        """
        return self.evaluate_tool(tool_id, policy.allowed_tools)
