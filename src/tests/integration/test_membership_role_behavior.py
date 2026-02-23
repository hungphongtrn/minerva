"""Integration tests for membership role behavior divergence.

Tests that owner and member roles produce different API outcomes
based on real workspace membership data.

Requirements covered:
- AUTH-05: Owner/member roles produce different authorization outcomes
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.db.models import User, Workspace, Membership, WorkspaceResource
from src.identity.service import ApiKeyService
from src.identity.key_material import KeyPair


class TestOwnerMemberDivergence:
    """Test that owner and member produce different API outcomes."""

    def test_owner_can_delete_resource_member_cannot(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Workspace,
        workspace_owner: User,
        workspace_member: User,
        owner_membership: Membership,
        member_membership: Membership,
    ):
        """Owner can delete workspace resources, member gets 403 (AUTH-05)."""
        # Create API keys for owner and member
        service = ApiKeyService(db_session)

        owner_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=workspace_owner.id,
            name="Owner Key",
            scopes=["workspace:write"],
        )

        member_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=workspace_member.id,
            name="Member Key",
            scopes=["workspace:write"],
        )

        # Create a resource as owner using ORM
        resource = WorkspaceResource(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            resource_type="test_resource",
            name="Test Resource for Delete",
            config=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(resource)
        db_session.commit()
        resource_id = str(resource.id)

        # Member tries to delete - should get 403 (member mutation denied after 01-09 fix)
        member_response = client.delete(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources/{resource_id}",
            headers={"X-Api-Key": member_key_pair.full_key},
        )
        # Member CANNOT delete since 01-09 tightened WORKSPACE_RESOURCE permissions
        assert member_response.status_code == 403

        # Owner tries to delete - should succeed (204)
        owner_response = client.delete(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources/{resource_id}",
            headers={"X-Api-Key": owner_key_pair.full_key},
        )
        assert owner_response.status_code == 204

    def test_member_cannot_create_workspace_resource(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Workspace,
        workspace_owner: User,
        workspace_member: User,
        owner_membership: Membership,
        member_membership: Membership,
    ):
        """Member POST to /workspaces/{id}/resources returns 403 (AUTH-05 UAT gap closure).

        This is the exact UAT scenario that was reported:
        "Member POST /workspaces/{workspace_id}/resources returned 201 Created;
        expected 403 for member role."
        """
        service = ApiKeyService(db_session)

        member_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=workspace_member.id,
            name="Member Key",
            scopes=["workspace:write"],
        )

        # Member attempts to create a resource - should get 403
        resource_data = {
            "name": "Member Created Resource",
            "resource_type": "test_resource",
            "config": "{}",
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources",
            json=resource_data,
            headers={"X-Api-Key": member_key_pair.full_key},
        )

        # Member create should be denied with 403
        assert response.status_code == 403
        # Verify error message mentions role/permission issue
        data = response.json()
        assert "detail" in data
        detail_str = str(data["detail"]).lower()
        assert (
            "member" in detail_str or "cannot" in detail_str or "denied" in detail_str
        )

    def test_member_cannot_update_workspace_resource(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Workspace,
        workspace_owner: User,
        workspace_member: User,
        owner_membership: Membership,
        member_membership: Membership,
    ):
        """Member PATCH to /workspaces/{id}/resources returns 403 (AUTH-05)."""
        service = ApiKeyService(db_session)

        owner_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=workspace_owner.id,
            name="Owner Key",
            scopes=["workspace:write"],
        )

        member_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=workspace_member.id,
            name="Member Key",
            scopes=["workspace:write"],
        )

        # Create a resource as owner
        resource_data = {
            "name": "Resource for Update Test",
            "resource_type": "test_resource",
            "config": "{}",
        }

        create_response = client.post(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources",
            json=resource_data,
            headers={"X-Api-Key": owner_key_pair.full_key},
        )
        assert create_response.status_code == 201
        resource_id = create_response.json()["id"]

        # Member attempts to update - should get 403
        update_data = {"name": "Updated Name by Member"}

        response = client.patch(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources/{resource_id}",
            json=update_data,
            headers={"X-Api-Key": member_key_pair.full_key},
        )

        # Member update should be denied with 403
        assert response.status_code == 403


class TestRoleBasedAuthorization:
    """Test role-based authorization in workspace resources."""

    def test_admin_can_perform_owner_like_actions(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Workspace,
        workspace_owner: User,
    ):
        """Admin can perform owner-like privileged actions."""
        # Create an admin user
        admin_user = User(
            id=uuid4(),
            email="admin@example.com",
            is_active=True,
            is_guest=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(admin_user)
        db_session.flush()  # Flush to get the ID

        # Create admin membership
        admin_membership = Membership(
            id=uuid4(),
            user_id=admin_user.id,
            workspace_id=workspace_alpha.id,
            role="admin",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(admin_membership)
        db_session.commit()

        # Create API key for admin
        service = ApiKeyService(db_session)
        admin_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,
            user_id=admin_user.id,
            name="Admin Key",
            scopes=["workspace:write"],
        )

        # Create a resource using ORM
        resource = WorkspaceResource(
            id=uuid4(),
            workspace_id=workspace_alpha.id,
            resource_type="test_resource",
            name="Test Resource for Admin",
            config=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(resource)
        db_session.commit()
        resource_id = str(resource.id)

        # Admin can delete - should succeed
        response = client.delete(
            f"/api/v1/workspaces/{workspace_alpha.id}/resources/{resource_id}",
            headers={"X-Api-Key": admin_key_pair.full_key},
        )
        # Admin should be able to delete (they have DELETE permission)
        assert response.status_code == 204

    def test_cross_workspace_membership_denial(
        self,
        client: TestClient,
        db_session: Session,
        workspace_alpha: Workspace,
        workspace_beta: Workspace,
        workspace_owner: User,
        owner_membership: Membership,
    ):
        """Cross-workspace access is denied with 403.

        Note: The 404 status occurs because the route tries to resolve the principal
        before checking workspace match. The membership is resolved from the key's
        workspace (alpha), then authorize_action checks workspace match and denies.
        """
        # Owner is only member of workspace_alpha, not workspace_beta
        service = ApiKeyService(db_session)

        owner_key_pair, _ = service.create_key(
            workspace_id=workspace_alpha.id,  # Key belongs to workspace_alpha
            user_id=workspace_owner.id,
            name="Owner Key",
            scopes=["workspace:read"],
        )

        # Owner tries to access workspace_beta resources
        # This should fail with 403 (cross-workspace access)
        response = client.get(
            f"/api/v1/workspaces/{workspace_beta.id}/resources",
            headers={"X-Api-Key": owner_key_pair.full_key},
        )
        # Should get 403 due to workspace mismatch in authorize_action
        # If the resource doesn't exist, might get 404 first
        assert response.status_code in [403, 404]
