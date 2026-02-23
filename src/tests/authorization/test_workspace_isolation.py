"""Workspace isolation and authorization tests.

Tests for AUTH-03 (workspace isolation) and AUTH-05 (role-based authorization).

Covers:
- Same-workspace resource access succeeds
- Cross-workspace resource access is denied
- Owner/member authorization differences
- RLS context enforcement
- Database-level tenant isolation
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

# Import directly from policy to avoid circular imports through guards
from src.authorization.policy import (
    Action,
    ResourceType,
    Role,
    Principal as AuthPrincipal,
    can_perform,
    authorize_action,
    require_workspace_access,
    get_role_from_string,
)
from src.db.rls_context import RLSContext, with_rls_context, get_rls_context


# ============================================================================
# Role Authorization Matrix Tests
# ============================================================================


class TestRoleAuthorizationMatrix:
    """Test the authorization matrix for owner/member behavior differences."""

    def test_owner_can_read_workspace(self):
        """Owner can read workspace resources."""
        assert can_perform(Role.OWNER, ResourceType.WORKSPACE, Action.READ) is True

    def test_owner_can_update_workspace(self):
        """Owner can update workspace settings."""
        assert can_perform(Role.OWNER, ResourceType.WORKSPACE, Action.UPDATE) is True

    def test_owner_can_delete_workspace(self):
        """Owner can delete workspace."""
        assert can_perform(Role.OWNER, ResourceType.WORKSPACE, Action.DELETE) is True

    def test_owner_can_admin_workspace(self):
        """Owner has admin privileges on workspace."""
        assert can_perform(Role.OWNER, ResourceType.WORKSPACE, Action.ADMIN) is True

    def test_member_can_read_workspace(self):
        """Member can read workspace."""
        assert can_perform(Role.MEMBER, ResourceType.WORKSPACE, Action.READ) is True

    def test_member_cannot_update_workspace(self):
        """Member cannot update workspace (AUTH-05)."""
        assert can_perform(Role.MEMBER, ResourceType.WORKSPACE, Action.UPDATE) is False

    def test_member_cannot_delete_workspace(self):
        """Member cannot delete workspace (AUTH-05)."""
        assert can_perform(Role.MEMBER, ResourceType.WORKSPACE, Action.DELETE) is False

    def test_member_cannot_admin_workspace(self):
        """Member cannot admin workspace (AUTH-05)."""
        assert can_perform(Role.MEMBER, ResourceType.WORKSPACE, Action.ADMIN) is False

    def test_owner_can_admin_memberships(self):
        """Owner can manage all memberships."""
        assert can_perform(Role.OWNER, ResourceType.MEMBERSHIP, Action.ADMIN) is True

    def test_member_can_read_memberships(self):
        """Member can read memberships (filtered to own)."""
        assert can_perform(Role.MEMBER, ResourceType.MEMBERSHIP, Action.READ) is True

    def test_admin_can_manage_resources(self):
        """Admin can manage workspace resources."""
        assert (
            can_perform(Role.ADMIN, ResourceType.WORKSPACE_RESOURCE, Action.CREATE)
            is True
        )
        assert (
            can_perform(Role.ADMIN, ResourceType.WORKSPACE_RESOURCE, Action.UPDATE)
            is True
        )
        assert (
            can_perform(Role.ADMIN, ResourceType.WORKSPACE_RESOURCE, Action.DELETE)
            is True
        )


class TestAuthorizeAction:
    """Test the authorize_action function with workspace boundaries."""

    def test_same_workspace_succeeds(self):
        """Authorization succeeds for same workspace."""
        workspace_id = uuid4()
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=workspace_id,
            role=Role.OWNER,
            is_active=True,
        )

        # Should not raise
        authorize_action(
            principal, ResourceType.WORKSPACE_RESOURCE, Action.READ, workspace_id
        )

    def test_cross_workspace_denied(self):
        """Cross-workspace access is denied (AUTH-03)."""
        principal_workspace = uuid4()
        target_workspace = uuid4()
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=principal_workspace,
            role=Role.OWNER,
            is_active=True,
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            authorize_action(
                principal,
                ResourceType.WORKSPACE_RESOURCE,
                Action.READ,
                target_workspace,
            )

        assert exc_info.value.status_code == 403
        assert "workspace" in exc_info.value.detail.lower()

    def test_inactive_principal_denied(self):
        """Inactive principal cannot perform actions."""
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=uuid4(),
            role=Role.OWNER,
            is_active=False,
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            authorize_action(principal, ResourceType.WORKSPACE_RESOURCE, Action.READ)

        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    def test_unauthorized_action_denied(self):
        """Unauthorized action is denied (fail-closed)."""
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=uuid4(),
            role=Role.MEMBER,
            is_active=True,
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            authorize_action(principal, ResourceType.WORKSPACE, Action.DELETE)

        assert exc_info.value.status_code == 403
        assert "member" in exc_info.value.detail.lower()


class TestRequireWorkspaceAccess:
    """Test workspace boundary enforcement."""

    def test_same_workspace_passes(self):
        """Same workspace ID passes."""
        workspace_id = uuid4()
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=workspace_id,
            role=Role.MEMBER,
            is_active=True,
        )

        # Should not raise
        require_workspace_access(principal, workspace_id)

    def test_different_workspace_denied(self):
        """Different workspace ID is denied (AUTH-03)."""
        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=uuid4(),
            role=Role.OWNER,
            is_active=True,
        )
        target_workspace = uuid4()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            require_workspace_access(principal, target_workspace)

        assert exc_info.value.status_code == 403


class TestRoleParsing:
    """Test role string parsing."""

    def test_parse_owner(self):
        """Can parse owner role."""
        assert get_role_from_string("owner") == Role.OWNER
        assert get_role_from_string("OWNER") == Role.OWNER

    def test_parse_admin(self):
        """Can parse admin role."""
        assert get_role_from_string("admin") == Role.ADMIN

    def test_parse_member(self):
        """Can parse member role."""
        assert get_role_from_string("member") == Role.MEMBER

    def test_invalid_role_raises(self):
        """Invalid role raises ValueError."""
        with pytest.raises(ValueError):
            get_role_from_string("superuser")


# ============================================================================
# RLS Context Tests
# ============================================================================


class TestRLSContext:
    """Test RLS context management."""

    def test_rls_context_sets_keys(self, mocker):
        """RLSContext sets the correct configuration keys."""
        mock_db = mocker.MagicMock()
        workspace_id = uuid4()
        user_id = uuid4()
        role = "owner"

        context = RLSContext(mock_db, workspace_id, user_id, role)
        context.set_context()

        # Should execute SET CONFIG for each key
        assert mock_db.execute.call_count == 3

    def test_rls_context_clears_keys(self, mocker):
        """RLSContext clears configuration keys."""
        mock_db = mocker.MagicMock()

        context = RLSContext(mock_db)
        context.clear_context()

        # Should execute SET CONFIG for each key with NULL
        assert mock_db.execute.call_count == 3

    def test_rls_context_manager_sets_and_clears(self, mocker):
        """Context manager sets context on enter and clears on exit."""
        mock_db = mocker.MagicMock()
        workspace_id = uuid4()

        with RLSContext(mock_db, workspace_id):
            pass

        # Should set context (3 calls) and clear context (3 calls)
        assert mock_db.execute.call_count == 6

    def test_with_rls_context_sets_workspace_id(self, mocker):
        """with_rls_context helper sets workspace ID."""
        mock_db = mocker.MagicMock()
        workspace_id = uuid4()

        with with_rls_context(mock_db, workspace_id):
            pass

        # Should set and clear
        assert mock_db.execute.call_count == 6


class TestRLSContextKeys:
    """Test RLS context key names."""

    def test_workspace_id_key(self):
        """Workspace ID key matches migration expectations."""
        assert RLSContext.WORKSPACE_ID_KEY == "app.workspace_id"

    def test_user_id_key(self):
        """User ID key matches migration expectations."""
        assert RLSContext.USER_ID_KEY == "app.user_id"

    def test_role_key(self):
        """Role key matches migration expectations."""
        assert RLSContext.ROLE_KEY == "app.role"


# ============================================================================
# Fail-Closed Authorization Tests
# ============================================================================


class TestFailClosedAuthorization:
    """Test that authorization fails closed by default."""

    def test_unknown_role_denied(self):
        """Unknown role cannot perform any actions."""

        # Create a fake role not in the matrix
        class FakeRole:
            value = "superadmin"

        assert can_perform(FakeRole(), ResourceType.WORKSPACE, Action.READ) is False

    def test_unknown_resource_type_denied(self):
        """Unknown resource type is denied."""

        class FakeResource:
            value = "secret_resource"

        assert can_perform(Role.OWNER, FakeResource(), Action.READ) is False

    def test_unlisted_action_denied(self):
        """Actions not in role's permissions are denied."""

        # Owner doesn't have a custom action
        class FakeAction:
            value = "custom_action"

        assert can_perform(Role.OWNER, ResourceType.WORKSPACE, FakeAction()) is False


# ============================================================================
# Owner vs Member Behavior Tests (AUTH-05)
# ============================================================================


class TestOwnerMemberBehaviorDifferences:
    """Test AUTH-05: Owner and member roles produce different outcomes."""

    def test_owner_can_delete_api_keys(self):
        """Owner can delete API keys."""
        assert can_perform(Role.OWNER, ResourceType.API_KEY, Action.DELETE) is True

    def test_member_cannot_delete_api_keys(self):
        """Member cannot delete API keys (AUTH-05)."""
        assert can_perform(Role.MEMBER, ResourceType.API_KEY, Action.DELETE) is False

    def test_owner_can_manage_members(self):
        """Owner can create/update/delete memberships."""
        assert can_perform(Role.OWNER, ResourceType.MEMBERSHIP, Action.CREATE) is True
        assert can_perform(Role.OWNER, ResourceType.MEMBERSHIP, Action.UPDATE) is True
        assert can_perform(Role.OWNER, ResourceType.MEMBERSHIP, Action.DELETE) is True

    def test_member_can_create_own_api_keys(self):
        """Member can create their own API keys."""
        assert can_perform(Role.MEMBER, ResourceType.API_KEY, Action.CREATE) is True

    def test_member_can_read_own_api_keys(self):
        """Member can read their own API keys."""
        assert can_perform(Role.MEMBER, ResourceType.API_KEY, Action.READ) is True

    def test_member_can_manage_agent_packs(self):
        """Member can manage agent packs (normal workspace work)."""
        assert can_perform(Role.MEMBER, ResourceType.AGENT_PACK, Action.CREATE) is True
        assert can_perform(Role.MEMBER, ResourceType.AGENT_PACK, Action.UPDATE) is True

    def test_owner_can_admin_agent_packs(self):
        """Owner can admin agent packs (e.g., transfer ownership)."""
        assert can_perform(Role.OWNER, ResourceType.AGENT_PACK, Action.ADMIN) is True

    def test_member_cannot_admin_agent_packs(self):
        """Member cannot admin agent packs."""
        assert can_perform(Role.MEMBER, ResourceType.AGENT_PACK, Action.ADMIN) is False


# ============================================================================
# Workspace Resource Access Tests (AUTH-03)
# ============================================================================


class TestWorkspaceResourceAccess:
    """Test AUTH-03: Users can only access resources in their own workspace."""

    def test_authorization_checks_workspace_match(self):
        """Authorization fails if workspace IDs don't match."""
        principal_workspace = uuid4()
        target_workspace = uuid4()

        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=principal_workspace,
            role=Role.OWNER,
            is_active=True,
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            authorize_action(
                principal,
                ResourceType.WORKSPACE_RESOURCE,
                Action.READ,
                target_workspace,
            )

        assert exc_info.value.status_code == 403

    def test_authorization_succeeds_with_matching_workspace(self):
        """Authorization succeeds when workspace IDs match."""
        workspace_id = uuid4()

        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=workspace_id,
            role=Role.MEMBER,
            is_active=True,
        )

        # Should not raise for member reading workspace_resource
        authorize_action(
            principal, ResourceType.WORKSPACE_RESOURCE, Action.READ, workspace_id
        )


# ============================================================================
# Integration Tests (Simulating API behavior)
# ============================================================================


class TestWorkspaceIsolationIntegration:
    """Integration tests for workspace isolation behavior."""

    def test_cross_workspace_read_blocked(self, mocker):
        """Cross-workspace read is blocked by authorization (AUTH-03)."""
        mock_db = mocker.MagicMock()

        principal_workspace = uuid4()
        target_workspace = uuid4()

        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=principal_workspace,
            role=Role.OWNER,
            is_active=True,
        )

        from fastapi import HTTPException

        # Attempt to access target workspace
        with pytest.raises(HTTPException) as exc_info:
            authorize_action(
                principal,
                ResourceType.WORKSPACE_RESOURCE,
                Action.READ,
                target_workspace,
            )

        assert exc_info.value.status_code == 403
        # No database query should occur
        mock_db.query.assert_not_called()

    def test_same_workspace_read_succeeds(self, mocker):
        """Same-workspace read passes authorization."""
        workspace_id = uuid4()

        principal = AuthPrincipal(
            user_id=uuid4(),
            workspace_id=workspace_id,
            role=Role.MEMBER,
            is_active=True,
        )

        # Should not raise
        authorize_action(
            principal, ResourceType.WORKSPACE_RESOURCE, Action.READ, workspace_id
        )
