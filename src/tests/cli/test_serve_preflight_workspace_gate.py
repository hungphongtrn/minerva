"""Regression tests for serve workspace preflight gate.

Tests prove `minerva serve` fails closed when the workspace-config check fails.
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest


class TestServePreflightWorkspaceGate:
    """Tests for workspace-config preflight gate in serve command."""

    def _create_check_mock(self, status, message, remediation=""):
        """Helper to create a properly configured check mock."""
        from src.services.preflight_service import CheckStatus

        check = MagicMock()
        check.status = CheckStatus.FAIL if status == "FAIL" else CheckStatus.PASS
        check.message = message
        check.remediation = remediation
        return check

    def test_serve_preflight_fails_when_workspace_check_fails(self):
        """Serve should fail closed when workspace-config check fails.

        Server must refuse to start when workspace check fails,
        preventing OSS deployments from running without valid workspace configuration.
        """
        from src.cli.commands import serve
        from src.services.preflight_service import CheckStatus

        # Arrange: Mock args with skip_preflight=False
        args = argparse.Namespace(
            host="0.0.0.0",
            port=8000,
            reload=False,
            skip_preflight=False,
        )

        # Create mock preflight service
        mock_service = MagicMock()

        # Schema check passes
        schema_check = MagicMock()
        schema_check.status = CheckStatus.PASS
        schema_check.message = "Database schema at head revision: abc123"

        # Workspace check fails
        workspace_check = MagicMock()
        workspace_check.status = CheckStatus.FAIL
        workspace_check.message = "MINERVA_WORKSPACE_ID not configured"
        workspace_check.remediation = (
            "Set MINERVA_WORKSPACE_ID. Run `minerva register` to get your workspace ID."
        )

        # Configure mock service
        mock_service.check_database_schema_current.return_value = schema_check
        mock_service.check_workspace_configured.return_value = workspace_check
        mock_service._get_picoclaw_snapshot_name.return_value = (
            None  # Skip snapshot check
        )

        # Act & Assert
        # Patch at the location where it's used (inside handle function)
        with patch(
            "src.services.preflight_service.PreflightService", return_value=mock_service
        ):
            with patch("src.cli.commands.serve.uvicorn.run") as mock_uvicorn:
                result = serve.handle(args)

                # Server should fail closed (return 1)
                assert result == 1, (
                    "Expected serve to return 1 when workspace check fails"
                )
                # Uvicorn should NOT have been called
                mock_uvicorn.assert_not_called()

    def test_serve_preflight_calls_workspace_check_on_success_path(self):
        """Serve should call workspace check and start server when all gates pass."""
        from src.cli.commands import serve
        from src.services.preflight_service import CheckStatus

        # Arrange: Mock args with skip_preflight=False
        args = argparse.Namespace(
            host="0.0.0.0",
            port=8000,
            reload=False,
            skip_preflight=False,
        )

        # Create mock preflight service
        mock_service = MagicMock()

        # All checks pass
        schema_check = MagicMock()
        schema_check.status = CheckStatus.PASS
        schema_check.message = "Database schema at head revision: abc123"

        workspace_check = MagicMock()
        workspace_check.status = CheckStatus.PASS
        workspace_check.message = (
            "Workspace 'test-workspace' configured with 1 agent pack(s)"
        )

        # Configure mock service
        mock_service.check_database_schema_current.return_value = schema_check
        mock_service.check_workspace_configured.return_value = workspace_check
        mock_service._get_picoclaw_snapshot_name.return_value = (
            None  # Skip snapshot check
        )

        # Act & Assert
        with patch(
            "src.services.preflight_service.PreflightService", return_value=mock_service
        ):
            with patch("src.cli.commands.serve.uvicorn.run") as mock_uvicorn:
                # Since uvicorn.run blocks, we need to simulate it returning
                # In actual test, we'll let it be called and verify the call
                serve.handle(args)

                # Uvicorn should have been called once
                mock_uvicorn.assert_called_once()
                # Should not return (blocks on uvicorn.run), but if it did, it would be 0
                # Note: In reality uvicorn.run() blocks, so this return path isn't hit

        # Verify workspace check was called
        mock_service.check_workspace_configured.assert_called_once()

    def test_serve_respects_skip_preflight_flag(self):
        """Serve should skip all preflight checks when --skip-preflight is set."""
        from src.cli.commands import serve

        # Arrange: Mock args with skip_preflight=True
        args = argparse.Namespace(
            host="0.0.0.0",
            port=8000,
            reload=False,
            skip_preflight=True,
        )

        # Act & Assert
        with patch(
            "src.services.preflight_service.PreflightService"
        ) as mock_service_class:
            with patch("src.cli.commands.serve.uvicorn.run") as mock_uvicorn:
                serve.handle(args)

                # PreflightService should NOT have been instantiated
                mock_service_class.assert_not_called()
                # Uvicorn should have been called directly
                mock_uvicorn.assert_called_once()

    def test_serve_fails_when_workspace_not_found(self):
        """Serve should fail when workspace_id points to non-existent workspace."""
        from src.cli.commands import serve
        from src.services.preflight_service import CheckStatus

        args = argparse.Namespace(
            host="0.0.0.0",
            port=8000,
            reload=False,
            skip_preflight=False,
        )

        mock_service = MagicMock()

        schema_check = MagicMock()
        schema_check.status = CheckStatus.PASS
        schema_check.message = "Database schema at head revision: abc123"

        # Workspace doesn't exist
        workspace_check = MagicMock()
        workspace_check.status = CheckStatus.FAIL
        workspace_check.message = "Workspace 'invalid-id' not found in database"
        workspace_check.remediation = "Run `minerva register` to create your workspace"

        mock_service.check_database_schema_current.return_value = schema_check
        mock_service.check_workspace_configured.return_value = workspace_check
        mock_service._get_picoclaw_snapshot_name.return_value = None

        with patch(
            "src.services.preflight_service.PreflightService", return_value=mock_service
        ):
            with patch("src.cli.commands.serve.uvicorn.run") as mock_uvicorn:
                result = serve.handle(args)

                assert result == 1
                mock_uvicorn.assert_not_called()

    def test_serve_fails_when_workspace_has_no_packs(self):
        """Serve should fail when workspace has no registered agent packs."""
        from src.cli.commands import serve
        from src.services.preflight_service import CheckStatus

        args = argparse.Namespace(
            host="0.0.0.0",
            port=8000,
            reload=False,
            skip_preflight=False,
        )

        mock_service = MagicMock()

        schema_check = MagicMock()
        schema_check.status = CheckStatus.PASS
        schema_check.message = "Database schema at head revision: abc123"

        # Workspace exists but has no packs
        workspace_check = MagicMock()
        workspace_check.status = CheckStatus.FAIL
        workspace_check.message = "Workspace has no registered agent packs"
        workspace_check.remediation = (
            "Run `minerva register` first to register an agent pack."
        )

        mock_service.check_database_schema_current.return_value = schema_check
        mock_service.check_workspace_configured.return_value = workspace_check
        mock_service._get_picoclaw_snapshot_name.return_value = None

        with patch(
            "src.services.preflight_service.PreflightService", return_value=mock_service
        ):
            with patch("src.cli.commands.serve.uvicorn.run") as mock_uvicorn:
                result = serve.handle(args)

                assert result == 1
                mock_uvicorn.assert_not_called()
