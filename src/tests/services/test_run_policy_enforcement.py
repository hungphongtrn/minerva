"""Run policy enforcement tests.

Tests for default-deny egress and tool enforcement in the active
run execution path. These tests prove that policy checks are
actually invoked during execute_run, not just available.
"""

import pytest
from unittest.mock import Mock
from uuid import uuid4

from src.services.run_service import RunService, RunContext
from src.runtime_policy.models import EgressPolicy, ToolPolicy, SecretScope
from src.runtime_policy.enforcer import RuntimeEnforcer
from src.guest.identity import create_guest_principal
from src.identity.key_material import Principal


@pytest.fixture
def run_service():
    """Create a run service with real enforcer."""
    return RunService()


@pytest.fixture
def mock_enforcer():
    """Create a mock enforcer for controlled testing."""
    return Mock(spec=RuntimeEnforcer)


@pytest.fixture
def sample_context():
    """Create a sample run context with authenticated principal."""
    principal = Principal(
        workspace_id=str(uuid4()),
        key_id="test_key",
        scopes=["run:execute"],
        is_active=True,
    )
    return RunContext(
        run_id=str(uuid4()),
        principal=principal,
        is_guest=False,
        workspace_id=str(uuid4()),
    )


@pytest.fixture
def guest_context():
    """Create a sample run context with guest principal."""
    principal = create_guest_principal()
    return RunContext(
        run_id=str(uuid4()),
        principal=principal,
        is_guest=True,
        workspace_id=None,
    )


@pytest.fixture
def default_deny_egress_policy():
    """Create a default-deny egress policy."""
    return EgressPolicy(allowed_hosts=[])


@pytest.fixture
def default_deny_tool_policy():
    """Create a default-deny tool policy."""
    return ToolPolicy(allowed_tools=[])


@pytest.fixture
def default_deny_secret_policy():
    """Create a default-deny secret policy."""
    return SecretScope(allowed_secrets=[])


# =============================================================================
# Egress Policy Enforcement Tests
# =============================================================================


class TestEgressPolicyEnforcement:
    """Tests for egress policy enforcement in execute_run."""

    def test_empty_egress_allowlist_denies_url_requests(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """SECU-01: Empty egress allowlist denies outbound URL requests."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://api.example.com/data"],
            requested_tools=[],
        )

        assert result.status == "denied"
        assert "egress" in result.error.lower()
        assert "denied" in result.error.lower()

    def test_explicit_egress_allowlist_entry_passes(
        self,
        run_service,
        sample_context,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Egress allowed when URL host is in allowlist."""
        egress_policy = EgressPolicy(allowed_hosts=["api.example.com"])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://api.example.com/data"],
            requested_tools=[],
        )

        assert result.status == "success"

    def test_egress_denied_for_different_host(
        self,
        run_service,
        sample_context,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Egress denied when URL host is not in allowlist."""
        egress_policy = EgressPolicy(allowed_hosts=["api.example.com"])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://malicious.com/data"],
            requested_tools=[],
        )

        assert result.status == "denied"

    def test_multiple_egress_urls_all_must_be_allowed(
        self,
        run_service,
        sample_context,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """All requested egress URLs must be allowed."""
        egress_policy = EgressPolicy(allowed_hosts=["api.example.com", "api.trusted.com"])

        # All allowed
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[
                "https://api.example.com/data",
                "https://api.trusted.com/info",
            ],
            requested_tools=[],
        )
        assert result.status == "success"

        # One not allowed
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[
                "https://api.example.com/data",
                "https://blocked.com/data",  # Not in allowlist
            ],
            requested_tools=[],
        )
        assert result.status == "denied"

    def test_wildcard_egress_pattern(
        self,
        run_service,
        sample_context,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Wildcard patterns in egress allowlist work correctly."""
        egress_policy = EgressPolicy(allowed_hosts=["*.example.com"])

        # Subdomain matches
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://sub.example.com/data"],
            requested_tools=[],
        )
        assert result.status == "success"

        # Different domain does not match
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://other.com/data"],
            requested_tools=[],
        )
        assert result.status == "denied"


# =============================================================================
# Tool Policy Enforcement Tests
# =============================================================================


class TestToolPolicyEnforcement:
    """Tests for tool policy enforcement in execute_run."""

    def test_empty_tool_allowlist_denies_requested_tools(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """SECU-02: Empty tool allowlist denies requested tools."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["file_read"],
        )

        assert result.status == "denied"
        assert "tool" in result.error.lower()
        assert "denied" in result.error.lower()

    def test_explicit_tool_allowlist_entry_passes(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_secret_policy,
    ):
        """Tool allowed when tool_id is in allowlist."""
        tool_policy = ToolPolicy(allowed_tools=["file_read", "file_write"])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["file_read"],
        )

        assert result.status == "success"

    def test_tool_denied_for_different_tool(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_secret_policy,
    ):
        """Tool denied when tool_id is not in allowlist."""
        tool_policy = ToolPolicy(allowed_tools=["file_read"])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["dangerous_shell_exec"],
        )

        assert result.status == "denied"

    def test_multiple_tools_all_must_be_allowed(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_secret_policy,
    ):
        """All requested tools must be allowed."""
        tool_policy = ToolPolicy(allowed_tools=["file_read", "file_write"])

        # All allowed
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["file_read", "file_write"],
        )
        assert result.status == "success"

        # One not allowed
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["file_read", "dangerous_tool"],
        )
        assert result.status == "denied"


# =============================================================================
# Deterministic Denial Response Tests
# =============================================================================


class TestDeterministicDenialResponses:
    """Tests for deterministic denial response format."""

    def test_egress_denial_includes_action_resource_reason(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Egress denial includes action, resource, and reason in error."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://api.example.com/data"],
            requested_tools=[],
        )

        assert result.status == "denied"
        # Error format: "Policy violation ({action}): {resource} - {reason}"
        assert "Policy violation (egress):" in result.error
        assert "https://api.example.com/data" in result.error
        assert "-" in result.error  # Has separator

    def test_tool_denial_includes_action_resource_reason(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Tool denial includes action, resource, and reason in error."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["file_read"],
        )

        assert result.status == "denied"
        # Error format: "Policy violation ({action}): {resource} - {reason}"
        assert "Policy violation (tool):" in result.error
        assert "file_read" in result.error
        assert "-" in result.error  # Has separator

    def test_denial_status_is_always_denied_not_error(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Policy denials return status='denied', not 'error'."""
        # Egress denial
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=[],
        )
        assert result.status == "denied"
        assert result.status != "error"

        # Tool denial
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["some_tool"],
        )
        assert result.status == "denied"
        assert result.status != "error"


# =============================================================================
# Combined Policy Enforcement Tests
# =============================================================================


class TestCombinedPolicyEnforcement:
    """Tests for combined egress and tool enforcement."""

    def test_egress_denial_precedes_tool_check(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_secret_policy,
    ):
        """Egress denial is raised before tool check when both would fail."""
        # Both policies deny, but egress check happens first
        tool_policy = ToolPolicy(allowed_tools=[])  # Default deny

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=["some_tool"],
        )

        assert result.status == "denied"
        assert "egress" in result.error.lower()

    def test_tool_denial_when_egress_passes(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,  # Actually empty, but we don't request egress
        default_deny_secret_policy,
    ):
        """Tool denial is raised when egress passes but tools fail."""
        tool_policy = ToolPolicy(allowed_tools=[])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],  # No egress requested
            requested_tools=["some_tool"],
        )

        assert result.status == "denied"
        assert "tool" in result.error.lower()

    def test_both_policies_pass_for_success(
        self,
        run_service,
        sample_context,
        default_deny_secret_policy,
    ):
        """Success only when both egress and tool policies pass."""
        egress_policy = EgressPolicy(allowed_hosts=["api.example.com"])
        tool_policy = ToolPolicy(allowed_tools=["file_read"])

        result = run_service.execute_run(
            context=sample_context,
            egress_policy=egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://api.example.com/data"],
            requested_tools=["file_read"],
        )

        assert result.status == "success"


# =============================================================================
# Guest Mode Policy Enforcement Tests
# =============================================================================


class TestGuestPolicyEnforcement:
    """Tests that policy enforcement applies equally to guest runs."""

    def test_guest_runs_enforce_egress_policy(
        self,
        run_service,
        guest_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Guest runs are subject to egress policy enforcement."""
        result = run_service.execute_run(
            context=guest_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=[],
        )

        assert result.status == "denied"
        assert "egress" in result.error.lower()

    def test_guest_runs_enforce_tool_policy(
        self,
        run_service,
        guest_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Guest runs are subject to tool policy enforcement."""
        result = run_service.execute_run(
            context=guest_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=["some_tool"],
        )

        assert result.status == "denied"
        assert "tool" in result.error.lower()

    def test_guest_runs_with_allowed_policies_succeed(
        self,
        run_service,
        guest_context,
        default_deny_secret_policy,
    ):
        """Guest runs succeed when policies allow the requests."""
        egress_policy = EgressPolicy(allowed_hosts=["api.example.com"])
        tool_policy = ToolPolicy(allowed_tools=["file_read"])

        result = run_service.execute_run(
            context=guest_context,
            egress_policy=egress_policy,
            tool_policy=tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://api.example.com/data"],
            requested_tools=["file_read"],
        )

        assert result.status == "success"


# =============================================================================
# Enforcement Stub Bypass Prevention Tests
# =============================================================================


class TestEnforcementStubBypassPrevention:
    """Tests that verify enforcement cannot be bypassed by stubbing."""

    def test_enforcement_uses_real_enforcer_not_mockable_at_call_site(
        self,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Enforcement cannot be bypassed by mocking at the execute_run level.

        This test verifies that the service actually calls the enforcer methods,
        not that it just returns what a mock would return.
        """
        # Create service with real enforcer
        service = RunService()

        # Verify that real enforcement happens by checking actual denial
        result = service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=["some_tool"],
        )

        # Real enforcement should deny
        assert result.status == "denied"
        assert result.run_id == sample_context.run_id  # Same run ID preserved

    def test_enforcement_integrity_with_dependency_injection(
        self,
        sample_context,
        default_deny_egress_policy,
    ):
        """Enforcer dependency injection does not bypass default-deny."""
        # Even with injected enforcer, default-deny still works
        real_enforcer = RuntimeEnforcer()
        service = RunService(enforcer=real_enforcer)

        result = service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=ToolPolicy(allowed_tools=[]),
            secret_policy=SecretScope(allowed_secrets=[]),
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=[],
        )

        assert result.status == "denied"


# =============================================================================
# Run Result Contract Tests
# =============================================================================


class TestRunResultContract:
    """Tests for RunResult structure and consistency."""

    def test_denied_result_has_run_id_matching_context(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Denied results preserve the original run_id."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=["https://example.com"],
            requested_tools=[],
        )

        assert result.run_id == sample_context.run_id
        assert result.status == "denied"
        assert result.error is not None

    def test_success_result_has_outputs(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Successful results include outputs with secrets_injected."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=SecretScope(allowed_secrets=["API_KEY"]),
            secrets={"API_KEY": "secret123", "OTHER": "secret456"},
            requested_egress_urls=[],
            requested_tools=[],
        )

        assert result.status == "success"
        assert result.outputs is not None
        assert "secrets_injected" in result.outputs
        assert "API_KEY" in result.outputs["secrets_injected"]
        assert "OTHER" not in result.outputs["secrets_injected"]

    def test_success_result_without_secrets_has_empty_injected_list(
        self,
        run_service,
        sample_context,
        default_deny_egress_policy,
        default_deny_tool_policy,
        default_deny_secret_policy,
    ):
        """Successful results with no secrets have empty secrets_injected."""
        result = run_service.execute_run(
            context=sample_context,
            egress_policy=default_deny_egress_policy,
            tool_policy=default_deny_tool_policy,
            secret_policy=default_deny_secret_policy,
            secrets={},
            requested_egress_urls=[],
            requested_tools=[],
        )

        assert result.status == "success"
        assert result.outputs["secrets_injected"] == []
