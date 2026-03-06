"""Smoke tests for gateway cutover verification.

These tests verify:
1. RunService uses Zeroclaw gateway client for execution (not PicoclawBridgeService)
2. Zeroclaw service is the primary execution path
3. OSS /runs routes use Zeroclaw gateway

This is a structural/code-level test (no Daytona dependency) to prove
the big-bang cutover from Picoclaw to Zeroclaw is complete.
"""

import ast
import inspect
from pathlib import Path

import pytest


class TestGatewayCutover:
    """Verify the runtime execution path has cut over to Zeroclaw."""

    def test_run_service_imports_zeroclaw_not_picoclaw(self):
        """RunService imports Zeroclaw gateway types, not Picoclaw bridge types."""
        # Read the run_service.py file
        run_service_path = Path("src/services/run_service.py")
        source = run_service_path.read_text()

        # Check that Zeroclaw is imported
        assert "from src.services.zeroclaw_gateway_service import" in source, (
            "RunService must import from zeroclaw_gateway_service"
        )

        # Check that Gateway types are imported (not Bridge types)
        assert "GatewayResult" in source, "RunService must use GatewayResult"
        assert "GatewayError" in source, "RunService must use GatewayError"
        assert "GatewayErrorType" in source, "RunService must use GatewayErrorType"
        assert "GatewayTokenBundle" in source, "RunService must use GatewayTokenBundle"

        # Check that old Bridge types are NOT used in the main code flow
        # (may still be present for backwards compat, but not primary usage)
        lines = source.split("\n")
        import_section = []
        in_imports = False
        for line in lines:
            if line.startswith("from ") or line.startswith("import "):
                in_imports = True
                import_section.append(line)
            elif in_imports and line.strip() and not line.startswith("#"):
                in_imports = False
            elif in_imports:
                import_section.append(line)

        import_text = "\n".join(import_section)

        # Should not import Bridge types from picoclaw_bridge_service
        assert "PicoclawBridgeService" not in import_text, (
            "RunService should not import PicoclawBridgeService"
        )
        assert "BridgeResult" not in import_text, (
            "RunService should not import BridgeResult"
        )
        assert "BridgeError" not in import_text, (
            "RunService should not import BridgeError"
        )
        assert "BridgeTokenBundle" not in import_text, (
            "RunService should not import BridgeTokenBundle"
        )

    def test_run_service_uses_zeroclaw_gateway_service(self):
        """RunService._execute_via_gateway instantiates ZeroclawGatewayService."""
        from src.services.run_service import RunService

        source = inspect.getsource(RunService._execute_via_bridge)

        # Should instantiate ZeroclawGatewayService
        assert "ZeroclawGatewayService()" in source, (
            "_execute_via_bridge must instantiate ZeroclawGatewayService"
        )

        # Should NOT instantiate PicoclawBridgeService
        assert "PicoclawBridgeService()" not in source, (
            "_execute_via_bridge must NOT instantiate PicoclawBridgeService"
        )

    def test_run_service_error_types_use_gateway_prefix(self):
        """RunService error type constants use GATEWAY_ prefix."""
        from src.services.run_service import RoutingErrorType

        # Should have GATEWAY_ error types
        assert hasattr(RoutingErrorType, "GATEWAY_HEALTH_CHECK_FAILED")
        assert hasattr(RoutingErrorType, "GATEWAY_AUTH_FAILED")
        assert hasattr(RoutingErrorType, "GATEWAY_TIMEOUT")
        assert hasattr(RoutingErrorType, "GATEWAY_TRANSPORT_ERROR")
        assert hasattr(RoutingErrorType, "GATEWAY_UPSTREAM_ERROR")
        assert hasattr(RoutingErrorType, "GATEWAY_MALFORMED_RESPONSE")

    def test_run_service_gateway_error_mapping(self):
        """RunService maps gateway errors to routing error types."""
        from src.services.run_service import RunService
        from src.services.zeroclaw_gateway_service import GatewayError, GatewayErrorType

        source = inspect.getsource(RunService._map_gateway_error_type)

        # Should map GatewayErrorType to GATEWAY_ routing errors
        assert "GatewayErrorType.HEALTH_CHECK_FAILED" in source
        assert "GATEWAY_HEALTH_CHECK_FAILED" in source

    def test_oss_runs_imports_zeroclaw_types(self):
        """OSS /runs route imports Zeroclaw types."""
        runs_path = Path("src/api/oss/routes/runs.py")
        source = runs_path.read_text()

        # Should import from zeroclaw_gateway_service
        assert "from src.services.zeroclaw_gateway_service import" in source, (
            "OSS runs must import from zeroclaw_gateway_service"
        )

        # Should use GatewayErrorType
        assert "GatewayErrorType" in source

    def test_zeroclaw_gateway_service_exists(self):
        """ZeroclawGatewayService file exists and is importable."""
        from src.services.zeroclaw_gateway_service import (
            ZeroclawGatewayService,
            GatewayResult,
            GatewayError,
            GatewayErrorType,
            GatewayTokenBundle,
        )

        # All main types should be importable
        assert ZeroclawGatewayService is not None
        assert GatewayResult is not None
        assert GatewayError is not None
        assert GatewayErrorType is not None
        assert GatewayTokenBundle is not None

    def test_zeroclaw_spec_is_loadable(self):
        """Zeroclaw spec file exists and loads correctly."""
        from src.integrations.zeroclaw.spec import load_zeroclaw_spec, ZeroclawSpec

        spec = load_zeroclaw_spec()

        assert spec is not None
        assert isinstance(spec, ZeroclawSpec)
        assert spec.version is not None
        assert spec.gateway.port is not None
        assert spec.gateway.health_path.startswith("/")
        assert spec.gateway.execute_path.startswith("/")
        assert spec.auth.mode in ("bearer", "none")
        assert spec.runtime.config_path.startswith("/")
        assert spec.runtime.start_command is not None

    def test_zeroclaw_config_path_outside_pack(self):
        """Zeroclaw config path respects mount isolation (outside /workspace/pack)."""
        from src.integrations.zeroclaw.spec import load_zeroclaw_spec

        spec = load_zeroclaw_spec()

        # Config path must NOT be under /workspace/pack (mount isolation)
        assert not spec.runtime.config_path.startswith("/workspace/pack"), (
            f"Config path {spec.runtime.config_path} violates mount isolation"
        )

    def test_daytona_provider_generates_zeroclaw_config(self):
        """Daytona provider has _generate_zeroclaw_config method."""
        from src.infrastructure.sandbox.providers.daytona import DaytonaSandboxProvider

        source = inspect.getsource(DaytonaSandboxProvider)

        # Should have Zeroclaw config generation
        assert "_generate_zeroclaw_config" in source, (
            "Daytona provider must have _generate_zeroclaw_config method"
        )

        # Should load spec for config generation
        assert "load_zeroclaw_spec" in source

    def test_orchestrator_generates_zeroclaw_bridge_config(self):
        """Orchestrator generates Zeroclaw-compatible runtime bridge config."""
        from src.services.sandbox_orchestrator_service import SandboxOrchestratorService

        source = inspect.getsource(
            SandboxOrchestratorService._generate_runtime_bridge_config
        )

        # Should load Zeroclaw spec
        assert "load_zeroclaw_spec" in source

        # Should include Zeroclaw-specific fields
        assert "auth_mode" in source
        assert "config_path" in source

    def test_cutover_complete_no_picoclaw_in_execution_path(self):
        """Execution path does not use PicoclawBridgeService.

        This is the definitive cutover verification.
        """
        # Read RunService source
        run_service_path = Path("src/services/run_service.py")
        run_service_source = run_service_path.read_text()

        # Parse to check for PicoclawBridgeService instantiation
        tree = ast.parse(run_service_source)

        # Find all class instantiations
        picoclaw_instantiations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "PicoclawBridgeService":
                        picoclaw_instantiations.append(node)

        # Should have ZERO PicoclawBridgeService instantiations
        assert len(picoclaw_instantiations) == 0, (
            "Cutover incomplete: RunService still instantiates PicoclawBridgeService"
        )

        # Should have at least one ZeroclawGatewayService instantiation
        zeroclaw_instantiations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == "ZeroclawGatewayService":
                        zeroclaw_instantiations.append(node)

        assert len(zeroclaw_instantiations) >= 1, (
            "RunService must instantiate ZeroclawGatewayService"
        )
