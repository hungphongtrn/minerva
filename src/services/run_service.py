"""Run execution service with guest persistence guard and policy hooks.

Provides run execution with:
- Workspace lifecycle integration for routing
- Sandbox gateway execution for in-sandbox runtime invocation
- Guest/non-guest persistence guards
- Runtime policy enforcement before network/tool/secret actions
- Scoped secret injection based on policy
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.guest.identity import GuestPrincipal, is_guest_principal
from src.identity.key_material import Principal as AuthPrincipal
from src.runtime_policy.enforcer import PolicyViolationError, RuntimeEnforcer
from src.runtime_policy.models import EgressPolicy, SecretScope, ToolPolicy
from src.services.runtime_persistence_service import (
    GuestPersistenceError,
    RuntimePersistenceService,
)
from src.services.sandbox_gateway_service import (
    GatewayError,
    GatewayErrorType,
    GatewayResult,
    GatewayTokenBundle,
    SandboxGatewayService,
)
from src.services.workspace_lifecycle_service import (
    LifecycleTarget,
    WorkspaceLifecycleService,
)


@dataclass
class RunContext:
    """Context for a run execution."""

    run_id: str
    principal: Any
    is_guest: bool
    workspace_id: str | None


@dataclass
class RunResult:
    """Result of a run execution."""

    run_id: str
    status: str
    error: str | None = None
    outputs: dict[str, Any] | None = None


class RoutingErrorType:
    """Error type constants for routing failures."""

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

    # Gateway execution errors (5xx range)
    GATEWAY_HEALTH_CHECK_FAILED = "gateway_health_check_failed"
    GATEWAY_AUTH_FAILED = "gateway_auth_failed"
    GATEWAY_TIMEOUT = "gateway_timeout"
    GATEWAY_TRANSPORT_ERROR = "gateway_transport_error"
    GATEWAY_UPSTREAM_ERROR = "gateway_upstream_error"
    GATEWAY_MALFORMED_RESPONSE = "gateway_malformed_response"


@dataclass
class RunRoutingResult:
    """Result of resolving routing target for a run."""

    success: bool
    workspace_id: str | None = None
    sandbox_id: str | None = None
    sandbox_state: str | None = None
    sandbox_health: str | None = None
    sandbox_url: str | None = None
    agent_pack_id: str | None = None
    lease_acquired: bool = False
    error: str | None = None
    error_type: str | None = None
    lifecycle_target: LifecycleTarget | None = None
    restore_in_progress: bool = False
    restore_checkpoint_id: str | None = None
    queued: bool = False
    run_id: str | None = None


class RunService:
    """Service for run execution with policy enforcement.

    Handles the core run execution flow including:
    - Workspace lifecycle resolution for sandbox routing
    - Guest mode detection and persistence guards
    - Runtime policy enforcement
    - Scoped secret injection
    - Single-attempt gateway execution (no nested retry loops)
    """

    def __init__(
        self,
        enforcer: RuntimeEnforcer | None = None,
        lifecycle_service: WorkspaceLifecycleService | None = None,
        persistence_service: RuntimePersistenceService | None = None,
    ):
        self.enforcer = enforcer or RuntimeEnforcer()
        self._lifecycle_service = lifecycle_service
        self._persistence_service = persistence_service

    def start_run(
        self,
        principal: Any,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: dict[str, Any],
        run_id: str | None = None,
    ) -> RunContext:
        """Start a new run with policy context."""
        if run_id is None:
            run_id = str(uuid4())

        return RunContext(
            run_id=run_id,
            principal=principal,
            is_guest=is_guest_principal(principal),
            workspace_id=getattr(principal, "workspace_id", None),
        )

    def persist_run(self, context: RunContext) -> None:
        """Persist run record — blocked for guests."""
        if context.is_guest:
            raise PermissionError(
                "Guest-mode runs cannot be persisted. "
                "Authenticate with an API key to enable persistence."
            )

    def persist_checkpoint(self, context: RunContext, checkpoint_data: dict[str, Any]) -> None:
        """Persist checkpoint record — blocked for guests."""
        if context.is_guest:
            raise PermissionError(
                "Guest-mode runs cannot create persistent checkpoints. "
                "Authenticate with an API key to enable checkpoint persistence."
            )

    def authorize_egress(self, context: RunContext, url: str, policy: EgressPolicy) -> None:
        """Authorize egress for this run."""
        self.enforcer.authorize_egress(url, policy)

    def authorize_tool(self, context: RunContext, tool_id: str, policy: ToolPolicy) -> None:
        """Authorize tool execution for this run."""
        self.enforcer.authorize_tool(tool_id, policy)

    def authorize_secret(
        self, context: RunContext, secret_name: str, allowed_secrets: list[str]
    ) -> None:
        """Authorize secret access for this run."""
        self.enforcer.authorize_secret(secret_name, allowed_secrets)

    def get_injected_secrets(
        self, context: RunContext, all_secrets: dict[str, Any], policy: SecretScope
    ) -> dict[str, Any]:
        """Get secrets filtered by policy for injection."""
        return self.enforcer.get_allowed_secrets(all_secrets, policy)

    def execute_run(
        self,
        context: RunContext,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: dict[str, Any],
        requested_egress_urls: list[str] | None = None,
        requested_tools: list[str] | None = None,
    ) -> RunResult:
        """Execute a run with full policy enforcement."""
        requested_egress_urls = requested_egress_urls or []
        requested_tools = requested_tools or []

        try:
            for url in requested_egress_urls:
                self.authorize_egress(context, url, egress_policy)
            for tool_id in requested_tools:
                self.authorize_tool(context, tool_id, tool_policy)

            injected_secrets = self.get_injected_secrets(context, secrets, secret_policy)

            if not context.is_guest:
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
                error=f"Execution failed: {e!s}",
            )

    # ── Routing ──────────────────────────────────────────────────

    async def resolve_routing_target(
        self,
        principal: Any,
        session: Session,
        auto_create_workspace: bool = True,
        agent_pack_id: str | None = None,
    ) -> RunRoutingResult:
        """Resolve workspace and sandbox routing target for a run.

        For guest principals, returns an ephemeral routing target
        without workspace persistence.
        """
        run_id = str(uuid4())

        if is_guest_principal(principal):
            return RunRoutingResult(
                success=True,
                sandbox_state="guest",
                sandbox_health="healthy",
                run_id=run_id,
            )

        try:
            lifecycle = self._lifecycle_service or WorkspaceLifecycleService(session=session)

            principal_workspace_id = getattr(principal, "workspace_id", None)
            principal_external_user_id = getattr(principal, "external_user_id", None)

            # OSS ExternalPrincipal path: explicit workspace_id + external_user_id
            if principal_workspace_id and principal_external_user_id:
                try:
                    workspace_uuid = UUID(principal_workspace_id)
                except ValueError:
                    return RunRoutingResult(
                        success=False,
                        error_type=RoutingErrorType.WORKSPACE_RESOLUTION_FAILED,
                        error=f"Invalid workspace_id format: {principal_workspace_id}",
                        run_id=run_id,
                    )

                target_workspace = lifecycle.get_workspace(workspace_uuid)
                if not target_workspace:
                    return RunRoutingResult(
                        success=False,
                        error_type=RoutingErrorType.WORKSPACE_RESOLUTION_FAILED,
                        error=f"Workspace not found: {principal_workspace_id}",
                        run_id=run_id,
                    )

                target = await lifecycle.resolve_target(
                    principal=principal,
                    auto_create=False,
                    acquire_lease=True,
                    run_id=run_id,
                    workspace=target_workspace,
                    agent_pack_id=agent_pack_id,
                    external_user_id=principal_external_user_id,
                )
                return self._process_routing_target(target, run_id, lifecycle)

            # Standard path: resolve workspace by principal owner
            target = await lifecycle.resolve_target(
                principal=principal,
                auto_create=auto_create_workspace,
                acquire_lease=True,
                run_id=run_id,
                agent_pack_id=agent_pack_id,
            )
            return self._process_routing_target(target, run_id, lifecycle)

        except Exception as e:
            return RunRoutingResult(
                success=False,
                error_type=RoutingErrorType.ROUTING_FAILED,
                error=f"Routing resolution failed: {e!s}",
                run_id=run_id,
            )

    def _process_routing_target(
        self,
        target: LifecycleTarget,
        run_id: str,
        lifecycle: WorkspaceLifecycleService,
    ) -> RunRoutingResult:
        """Process a resolved lifecycle target into a routing result."""
        # Check for restore in progress
        if target.workspace:
            try:
                if lifecycle.is_restore_in_progress(target.workspace.id):
                    return RunRoutingResult(
                        success=True,
                        workspace_id=str(target.workspace.id),
                        sandbox_state="restoring",
                        sandbox_health="unknown",
                        restore_in_progress=True,
                        restore_checkpoint_id=lifecycle.get_restore_checkpoint_id(
                            target.workspace.id
                        ),
                        queued=True,
                        lifecycle_target=target,
                        run_id=run_id,
                    )
            except Exception:
                pass

        if not target.workspace:
            return RunRoutingResult(
                success=False,
                error_type=RoutingErrorType.WORKSPACE_RESOLUTION_FAILED,
                error=target.error or "Workspace resolution failed",
                run_id=run_id,
            )

        if not target.routing_result or not target.routing_result.success:
            error_msg = target.error or (
                target.routing_result.message
                if target.routing_result
                else "Routing failed: no healthy sandbox available"
            )
            return RunRoutingResult(
                success=False,
                workspace_id=str(target.workspace.id),
                error_type=self._categorize_routing_error(error_msg),
                error=error_msg,
                lease_acquired=target.lease_acquired,
                lifecycle_target=target,
                run_id=run_id,
            )

        routing_result = target.routing_result
        if not routing_result.sandbox:
            return RunRoutingResult(
                success=False,
                workspace_id=str(target.workspace.id),
                error_type=self._categorize_routing_error(routing_result.message or ""),
                error=routing_result.message or "No sandbox provisioned",
                lease_acquired=target.lease_acquired,
                lifecycle_target=target,
                run_id=run_id,
            )

        # Extract sandbox info
        sandbox = routing_result.sandbox
        sandbox_state = self._extract_enum_value(getattr(sandbox, "state", None))
        sandbox_health = self._extract_enum_value(getattr(sandbox, "health_status", None))

        if sandbox_state == "restoring":
            return RunRoutingResult(
                success=True,
                workspace_id=str(target.workspace.id),
                sandbox_id=str(sandbox.id),
                sandbox_state=sandbox_state,
                sandbox_health=sandbox_health,
                restore_in_progress=True,
                queued=True,
                lease_acquired=target.lease_acquired,
                lifecycle_target=target,
                run_id=run_id,
            )

        return RunRoutingResult(
            success=True,
            workspace_id=str(target.workspace.id),
            sandbox_id=str(sandbox.id),
            sandbox_state=sandbox_state or "unknown",
            sandbox_health=sandbox_health,
            sandbox_url=getattr(sandbox, "gateway_url", None),
            agent_pack_id=str(sandbox.agent_pack_id) if sandbox.agent_pack_id else None,
            lease_acquired=target.lease_acquired,
            lifecycle_target=target,
            run_id=run_id,
        )

    # ── Execute with routing ────────────────────────────────────

    async def execute_with_routing(
        self,
        principal: Any,
        session: Session,
        egress_policy: EgressPolicy,
        tool_policy: ToolPolicy,
        secret_policy: SecretScope,
        secrets: dict[str, Any],
        requested_egress_urls: list[str] | None = None,
        requested_tools: list[str] | None = None,
        agent_pack_id: str | None = None,
        input_message: str | None = None,
        session_id: str | None = None,
    ) -> RunResult:
        """Execute a run with full routing and policy enforcement.

        This is the main entrypoint for run execution.
        Gateway execution is single-attempt — if it fails, the run fails.
        No nested recovery loops that could spawn multiple sandboxes.
        """
        persistence = self._persistence_service or RuntimePersistenceService(session)

        # Resolve routing target
        routing = await self.resolve_routing_target(
            principal, session, agent_pack_id=agent_pack_id
        )

        if not routing.success:
            self._release_lease_if_held(routing, session)
            result = RunResult(
                run_id=routing.run_id or str(uuid4()),
                status="error",
                error=routing.error or "Failed to resolve routing target",
            )
            result.outputs = {"routing_error_type": routing.error_type}
            return result

        # Start the run
        context = self.start_run(
            principal=principal,
            egress_policy=egress_policy,
            tool_policy=tool_policy,
            secret_policy=secret_policy,
            secrets=secrets,
            run_id=routing.run_id,
        )
        if routing.workspace_id:
            context.workspace_id = routing.workspace_id

        # Create run session for non-guest runs
        run_session_id = self._create_run_session(
            context,
            routing,
            principal,
            persistence,
            input_message,
            requested_egress_urls,
            requested_tools,
        )

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

        if result.outputs is None:
            result.outputs = {}
        result.outputs["routing"] = {
            "workspace_id": routing.workspace_id,
            "sandbox_id": routing.sandbox_id,
            "sandbox_state": routing.sandbox_state,
            "sandbox_health": routing.sandbox_health,
            "lease_acquired": routing.lease_acquired,
        }

        # Execute via ZeroClaw gateway (single attempt, no recovery loop)
        if routing.sandbox_id and input_message:
            gateway_result = await self._execute_via_gateway(
                routing=routing,
                message=input_message,
                is_guest=context.is_guest,
                session=session,
                session_id=session_id,
                sender_id=(
                    "guest" if context.is_guest else getattr(principal, "external_user_id", None)
                ),
            )
            self._apply_gateway_result(result, gateway_result)

        # Update run session state
        self._finalize_run_session(
            run_session_id, context, routing, result, principal, persistence
        )

        # Release lease deterministically
        self._release_lease_if_held(routing, session)

        return result

    # ── Gateway execution (single-attempt) ──────────────────────

    async def _execute_via_gateway(
        self,
        routing: RunRoutingResult,
        message: str,
        is_guest: bool,
        session: Session,
        session_id: str | None = None,
        sender_id: str | None = None,
    ) -> GatewayResult:
        """Execute request via ZeroClaw gateway — single attempt, no nested retries.

        This method intentionally does NOT retry or reprovision on failure.
        If the gateway is unreachable, the run fails. The orchestrator's own
        retry loop handles provisioning; we don't layer another retry on top.
        """
        sandbox_url = self._get_authoritative_sandbox_url(routing)

        if not sandbox_url:
            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TRANSPORT_ERROR,
                    message="Sandbox gateway URL not available",
                    remediation="Sandbox may not be fully provisioned.",
                ),
            )

        if self._is_local_compose_url(sandbox_url):
            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.TRANSPORT_ERROR,
                    message="Local compose sandbox has no ZeroClaw gateway.",
                    remediation="Use Daytona sandbox provider for full execution.",
                ),
            )

        token_bundle = self._resolve_gateway_tokens(routing, session)
        if not token_bundle or not token_bundle.current:
            return GatewayResult(
                success=False,
                error=GatewayError(
                    error_type=GatewayErrorType.AUTH_FAILED,
                    message="No valid token resolved from sandbox metadata",
                    remediation="Check sandbox provisioning configuration.",
                ),
            )

        session_key = self._generate_session_key(
            workspace_id=routing.workspace_id,
            agent_pack_id=(
                routing.lifecycle_target.agent_pack_id if routing.lifecycle_target else None
            ),
            run_id=str(uuid4()),
            is_guest=is_guest,
            session_id=session_id,
        )

        gateway_service = SandboxGatewayService()
        return await gateway_service.execute(
            sandbox_url=sandbox_url,
            message=message,
            session_key=session_key,
            token_bundle=token_bundle,
            workspace_id=routing.workspace_id,
            agent_pack_id=(
                routing.lifecycle_target.agent_pack_id if routing.lifecycle_target else None
            ),
            run_id=session_key.split(":")[-1],
            sender_id=sender_id,
            session_id=session_id,
        )

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_enum_value(val: Any) -> str | None:
        """Extract string value from enum or raw value."""
        if val is None:
            return None
        return str(val.value) if hasattr(val, "value") else str(val)

    def _get_principal_id(self, principal: Any) -> str | None:
        """Extract principal ID from principal object."""
        for attr in ("user_id", "id", "principal_id"):
            val = getattr(principal, attr, None)
            if val is not None:
                return str(val)
        return None

    def _generate_session_key(
        self,
        workspace_id: str | None,
        agent_pack_id: str | None,
        run_id: str,
        is_guest: bool,
        session_id: str | None = None,
    ) -> str:
        """Generate deterministic session key scoped to workspace+pack."""
        if is_guest:
            return f"minerva:guest:{run_id}"
        pack_scope = agent_pack_id or "default"
        continuity_key = session_id if session_id else run_id
        return f"minerva:{workspace_id}:{pack_scope}:{continuity_key}"

    def _get_authoritative_sandbox_url(self, routing: RunRoutingResult) -> str | None:
        """Get the authoritative sandbox gateway URL."""
        if routing.sandbox_url:
            return routing.sandbox_url
        if routing.lifecycle_target and routing.lifecycle_target.routing_result:
            sandbox = routing.lifecycle_target.routing_result.sandbox
            if sandbox and hasattr(sandbox, "gateway_url") and sandbox.gateway_url:
                return sandbox.gateway_url
        return None

    @staticmethod
    def _is_local_compose_url(sandbox_url: str) -> bool:
        """Check if the sandbox URL is from local compose provider."""
        if not sandbox_url:
            return False
        return sandbox_url.startswith("http://local-sandbox-") or sandbox_url.startswith(
            "https://local-sandbox-"
        )

    def _resolve_gateway_tokens(
        self, routing: RunRoutingResult, session: Session
    ) -> GatewayTokenBundle | None:
        """Resolve gateway auth tokens from sandbox metadata."""
        if not routing.sandbox_id:
            return None
        try:
            from src.db.repositories.sandbox_instance_repository import (
                SandboxInstanceRepository,
            )

            repo = SandboxInstanceRepository(session)
            token_data = repo.resolve_bridge_tokens(UUID(routing.sandbox_id))
            if not token_data or not token_data.get("current"):
                return None

            return GatewayTokenBundle(
                current=token_data["current"],
                previous=token_data.get("previous"),
                previous_expires_at=token_data.get("previous_expires_at"),
            )
        except Exception:
            return None

    def _apply_gateway_result(self, result: RunResult, gateway_result: GatewayResult) -> None:
        """Apply gateway execution result to the run result."""
        if result.outputs is None:
            result.outputs = {}

        if gateway_result.success:
            result.outputs["gateway"] = {
                "success": True,
                "output": gateway_result.output,
            }
            if gateway_result.output:
                result.outputs["final_output"] = gateway_result.output.get(
                    "message"
                ) or gateway_result.output.get("content")
        else:
            result.status = "error"
            gw_error = (
                gateway_result.error.message
                if gateway_result.error
                else "Gateway execution failed"
            )
            result.error = gw_error
            result.outputs["routing_error_type"] = self._map_gateway_error_type(
                gateway_result.error
            )
            result.outputs["gateway"] = {
                "success": False,
                "error": (gateway_result.error.to_dict() if gateway_result.error else None),
            }

    def _create_run_session(
        self,
        context: RunContext,
        routing: RunRoutingResult,
        principal: Any,
        persistence: RuntimePersistenceService,
        input_message: str | None,
        requested_egress_urls: list[str] | None,
        requested_tools: list[str] | None,
    ) -> UUID | None:
        """Create run session for non-guest runs."""
        if context.is_guest or not routing.workspace_id or not routing.sandbox_id:
            return None
        try:
            return persistence.create_run_session(
                workspace_id=UUID(routing.workspace_id),
                run_id=context.run_id,
                principal_id=self._get_principal_id(principal),
                principal_type="user",
                is_guest=False,
                request_payload={
                    "input": input_message,
                    "egress_urls": requested_egress_urls,
                    "tools": requested_tools,
                },
                sandbox_id=UUID(routing.sandbox_id),
            )
        except (GuestPersistenceError, Exception):
            return None

    def _finalize_run_session(
        self,
        run_session_id: UUID | None,
        context: RunContext,
        routing: RunRoutingResult,
        result: RunResult,
        principal: Any,
        persistence: RuntimePersistenceService,
    ) -> None:
        """Update run session state based on result (non-guest only)."""
        if not run_session_id or context.is_guest:
            return
        try:
            principal_id = self._get_principal_id(principal)
            workspace_uuid = UUID(routing.workspace_id) if routing.workspace_id else None
            if result.status == "success":
                persistence.mark_run_completed(
                    run_session_id=run_session_id,
                    workspace_id=workspace_uuid,
                    run_id=context.run_id,
                    result_payload=result.outputs,
                    principal_id=principal_id,
                    is_guest=False,
                )
            else:
                persistence.mark_run_failed(
                    run_session_id=run_session_id,
                    workspace_id=workspace_uuid,
                    run_id=context.run_id,
                    error_message=result.error or "Run failed",
                    error_code=(
                        result.outputs.get("routing_error_type") if result.outputs else None
                    ),
                    principal_id=principal_id,
                    is_guest=False,
                )
        except Exception:
            pass

    def _release_lease_if_held(self, routing: RunRoutingResult, session: Session) -> None:
        """Release lease deterministically."""
        if not routing.lease_acquired or not routing.workspace_id:
            return
        try:
            from src.db.repositories.workspace_lease_repository import (
                WorkspaceLeaseRepository,
            )

            lease_repo = WorkspaceLeaseRepository(session)
            lease_repo.release_lease(
                workspace_id=UUID(routing.workspace_id),
                holder_run_id=routing.run_id,
            )
        except Exception:
            pass

    def _map_gateway_error_type(self, error: GatewayError | None) -> str:
        """Map gateway error to routing error type for API mapping."""
        if not error:
            return RoutingErrorType.ROUTING_FAILED
        mapping = {
            GatewayErrorType.HEALTH_CHECK_FAILED: RoutingErrorType.GATEWAY_HEALTH_CHECK_FAILED,
            GatewayErrorType.AUTH_FAILED: RoutingErrorType.GATEWAY_AUTH_FAILED,
            GatewayErrorType.TIMEOUT: RoutingErrorType.GATEWAY_TIMEOUT,
            GatewayErrorType.TRANSPORT_ERROR: RoutingErrorType.GATEWAY_TRANSPORT_ERROR,
            GatewayErrorType.UPSTREAM_ERROR: RoutingErrorType.GATEWAY_UPSTREAM_ERROR,
            GatewayErrorType.MALFORMED_RESPONSE: RoutingErrorType.GATEWAY_MALFORMED_RESPONSE,
        }
        return mapping.get(error.error_type, RoutingErrorType.ROUTING_FAILED)

    def _categorize_routing_error(self, error_msg: str) -> str:
        """Categorize routing error message into deterministic error type."""
        if not error_msg:
            return RoutingErrorType.ROUTING_FAILED

        msg = error_msg.lower()

        if "agent pack not found" in msg:
            return RoutingErrorType.PACK_NOT_FOUND
        if "does not belong to workspace" in msg:
            return RoutingErrorType.PACK_WORKSPACE_MISMATCH
        if "is not valid" in msg:
            return RoutingErrorType.PACK_INVALID
        if "is not active" in msg or "stale" in msg:
            return RoutingErrorType.PACK_STALE
        if "lease" in msg and ("conflict" in msg or "acquire" in msg):
            return RoutingErrorType.LEASE_CONFLICT
        if "provision" in msg and "failed" in msg:
            return RoutingErrorType.SANDBOX_PROVISION_FAILED
        if "failed to provision" in msg:
            return RoutingErrorType.SANDBOX_PROVISION_FAILED
        if "daytona" in msg and ("error" in msg or "failed" in msg):
            return RoutingErrorType.SANDBOX_PROVISION_FAILED
        if "workspace" in msg and "resolution" in msg and "not found" in msg:
            return RoutingErrorType.WORKSPACE_RESOLUTION_FAILED

        return RoutingErrorType.ROUTING_FAILED


# Type alias for any principal
AnyPrincipal = AuthPrincipal | GuestPrincipal
