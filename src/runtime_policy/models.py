"""Runtime policy models for access control.

Defines data structures for egress, tool, and secret policies.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class PolicyDecision:
    """Result of a policy evaluation."""

    allowed: bool
    reason: str


@dataclass
class EgressPolicy:
    """Policy for network egress control.

    Defines which external hosts are allowed for outbound connections.
    """

    allowed_hosts: List[str]

    def __post_init__(self):
        # Normalize hosts to lowercase
        self.allowed_hosts = [h.lower().strip() for h in self.allowed_hosts]


@dataclass
class ToolPolicy:
    """Policy for tool access control.

    Defines which tools are allowed for agent execution.
    """

    allowed_tools: List[str]

    def __post_init__(self):
        # Normalize tool IDs
        self.allowed_tools = [t.lower().strip() for t in self.allowed_tools]


@dataclass
class SecretScope:
    """Policy for secret access control.

    Defines which secrets can be injected into runs.
    """

    allowed_secrets: List[str]

    def __post_init__(self):
        # Normalize secret names
        self.allowed_secrets = [s.strip() for s in self.allowed_secrets]


@dataclass
class RuntimePolicy:
    """Complete runtime policy for a workspace or agent pack.

    Combines egress, tool, and secret policies into a single policy object.
    """

    egress: EgressPolicy
    tools: ToolPolicy
    secrets: SecretScope

    @classmethod
    def default_deny(cls) -> "RuntimePolicy":
        """Create a default-deny policy that blocks everything."""
        return cls(
            egress=EgressPolicy(allowed_hosts=[]),
            tools=ToolPolicy(allowed_tools=[]),
            secrets=SecretScope(allowed_secrets=[]),
        )
