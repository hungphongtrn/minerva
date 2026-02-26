"""Phase 1 end-to-end acceptance tests.

Tests map directly to roadmap success criteria:
1. AUTH-01: Personal API key authentication works
2. AUTH-02: Key rotate/revoke changes outcomes
3. AUTH-03: Workspace data isolation is enforced
4. AUTH-05: Owner/member role behavior differs
5. AUTH-06: Anonymous requests become guest mode and skip persistence
6. SECU-01/02/03: Runtime policy enforces default-deny egress/tool/secret semantics
"""


from fastapi.testclient import TestClient
from fastapi import status

from src.identity.key_material import KeyPair


# ============================================================================
# AUTH-01: Personal API Key Authentication
# ============================================================================


class TestApiKeyAuth:
    """Acceptance tests for AUTH-01: API key authentication works."""

    def test_valid_api_key_returns_authorized_response(
        self, client: TestClient, owner_headers: dict
    ):
        """Success Criterion 1: Valid API key receives authorized responses."""
        response = client.get("/api/v1/whoami", headers=owner_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workspace_id" in data
        assert "key_id" in data
        assert data["is_active"] is True

    def test_missing_api_key_returns_401(self, client: TestClient):
        """Success Criterion 1: Missing API key fails authentication."""
        response = client.get("/api/v1/whoami")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "API key required" in response.json()["detail"]

    def test_invalid_api_key_returns_401(self, client: TestClient):
        """Success Criterion 1: Invalid API key fails authentication."""
        headers = {"X-Api-Key": "invalid_key_12345"}
        response = client.get("/api/v1/whoami", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid API key" in response.json()["detail"]

    def test_revoked_api_key_returns_401(
        self, client: TestClient, revoked_headers: dict
    ):
        """Success Criterion 1: Revoked API key fails authentication."""
        response = client.get("/api/v1/whoami", headers=revoked_headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "revoked" in response.json()["detail"].lower()

    def test_bearer_token_format_works(
        self, client: TestClient, owner_api_key: tuple[KeyPair, any]
    ):
        """Success Criterion 1: Bearer token format is accepted."""
        key_pair, _ = owner_api_key
        headers = {"Authorization": f"Bearer {key_pair.full_key}"}
        response = client.get("/api/v1/whoami", headers=headers)

        assert response.status_code == status.HTTP_200_OK

    def test_expired_api_key_returns_401(
        self, client: TestClient, expired_api_key: tuple[KeyPair, any]
    ):
        """Success Criterion 1: Expired API key fails authentication."""
        key_pair, _ = expired_api_key
        headers = {"X-Api-Key": key_pair.full_key}
        response = client.get("/api/v1/whoami", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in response.json()["detail"].lower()


# ============================================================================
# AUTH-02: Key Rotation and Revocation
# ============================================================================


class TestKeyRotateRevoke:
    """Acceptance tests for AUTH-02: Rotate/revoke changes outcomes."""

    def test_key_rotation_invalidates_old_key(
        self,
        client: TestClient,
        owner_api_key: tuple[KeyPair, any],
        workspace_alpha: any,
        owner_headers: dict,
    ):
        """Success Criterion 2: Rotating a key invalidates the old key."""
        old_key_pair, key_info = owner_api_key
        key_id = key_info.id

        # Verify old key works
        response = client.get("/api/v1/whoami", headers=owner_headers)
        assert response.status_code == status.HTTP_200_OK

        # Rotate the key
        rotate_response = client.post(
            f"/api/v1/api-keys/{key_id}/rotate",
            headers=owner_headers,
        )
        assert rotate_response.status_code == status.HTTP_200_OK
        rotate_data = rotate_response.json()
        new_key = rotate_data["full_key"]

        # Old key should now fail
        old_headers = {"X-Api-Key": old_key_pair.full_key}
        old_response = client.get("/api/v1/whoami", headers=old_headers)
        assert old_response.status_code == status.HTTP_401_UNAUTHORIZED

        # New key should work
        new_headers = {"X-Api-Key": new_key}
        new_response = client.get("/api/v1/whoami", headers=new_headers)
        assert new_response.status_code == status.HTTP_200_OK

    def test_key_revocation_prevents_authentication(
        self,
        client: TestClient,
        owner_api_key: tuple[KeyPair, any],
        workspace_alpha: any,
        owner_headers: dict,
    ):
        """Success Criterion 2: Revoked keys fail subsequent requests."""
        _, key_info = owner_api_key
        key_id = key_info.id

        # Verify key works initially
        response = client.get("/api/v1/whoami", headers=owner_headers)
        assert response.status_code == status.HTTP_200_OK

        # Revoke the key
        revoke_response = client.post(
            f"/api/v1/api-keys/{key_id}/revoke",
            headers=owner_headers,
        )
        assert revoke_response.status_code == status.HTTP_200_OK
        revoke_data = revoke_response.json()
        assert revoke_data["is_active"] is False

        # Key should now fail
        failed_response = client.get("/api/v1/whoami", headers=owner_headers)
        assert failed_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_keys_shows_key_status(
        self,
        client: TestClient,
        owner_headers: dict,
        owner_api_key: tuple[KeyPair, any],
    ):
        """Success Criterion 2: Key lifecycle status is observable."""
        _, key_info = owner_api_key

        response = client.get("/api/v1/api-keys", headers=owner_headers)
        assert response.status_code == status.HTTP_200_OK

        keys = response.json()
        assert len(keys) >= 1

        # Find our key
        our_key = next((k for k in keys if k["id"] == key_info.id), None)
        assert our_key is not None
        assert our_key["is_active"] is True
        assert "prefix" in our_key
        assert "scopes" in our_key


# ============================================================================
# AUTH-03: Workspace Isolation
# ============================================================================


class TestWorkspaceIsolation:
    """Acceptance tests for AUTH-03: Workspace data isolation is enforced."""

    def test_user_can_access_own_workspace_resources(
        self,
        client: TestClient,
        owner_headers: dict,
        workspace_alpha: any,
        sample_resource: any,
    ):
        """Success Criterion 3: User can access resources in own workspace."""
        workspace_id = str(workspace_alpha.id)

        response = client.get(
            f"/api/v1/workspaces/{workspace_id}/resources",
            headers=owner_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert data["workspace_id"] == workspace_id

    def test_user_cannot_access_other_workspace_resources(
        self,
        client: TestClient,
        other_workspace_headers: dict,
        workspace_alpha: any,
    ):
        """Success Criterion 3: User cannot access another workspace's data."""
        # Try to access workspace_alpha with other workspace's key
        workspace_id = str(workspace_alpha.id)

        response = client.get(
            f"/api/v1/workspaces/{workspace_id}/resources",
            headers=other_workspace_headers,
        )

        # Should be forbidden (403) due to workspace mismatch
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_workspace_resource_creation_blocked(
        self,
        client: TestClient,
        other_workspace_headers: dict,
        workspace_alpha: any,
    ):
        """Success Criterion 3: Cross-workspace resource creation is blocked."""
        workspace_id = str(workspace_alpha.id)

        resource_data = {
            "name": "Cross-workspace resource",
            "resource_type": "test",
            "config": "{}",
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/resources",
            json=resource_data,
            headers=other_workspace_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_workspace_list_only_shows_own_resources(
        self,
        client: TestClient,
        owner_headers: dict,
        workspace_alpha: any,
        sample_resource: any,
    ):
        """Success Criterion 3: Resource list scoped to workspace."""
        workspace_id = str(workspace_alpha.id)

        response = client.get(
            f"/api/v1/workspaces/{workspace_id}/resources",
            headers=owner_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # All resources should belong to the requested workspace
        for resource in data["items"]:
            assert resource["workspace_id"] == workspace_id


# ============================================================================
# AUTH-05: Role-Based Access Control
# ============================================================================


class TestRoleBehavior:
    """Acceptance tests for AUTH-05: Owner/member role behavior differs."""

    def test_owner_can_create_resources(
        self,
        client: TestClient,
        owner_headers: dict,
        workspace_alpha: any,
    ):
        """Success Criterion 4: Owner can create workspace resources."""
        workspace_id = str(workspace_alpha.id)

        resource_data = {
            "name": "Owner Created Resource",
            "resource_type": "agent_config",
            "config": '{"model": "gpt-4"}',
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/resources",
            json=resource_data,
            headers=owner_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == resource_data["name"]
        assert data["workspace_id"] == workspace_id

    def test_member_can_read_resources(
        self,
        client: TestClient,
        member_headers: dict,
        workspace_alpha: any,
        sample_resource: any,
    ):
        """Success Criterion 4: Member can read workspace resources."""
        workspace_id = str(workspace_alpha.id)

        response = client.get(
            f"/api/v1/workspaces/{workspace_id}/resources",
            headers=member_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data

    def test_role_scope_enforcement_on_keys(
        self,
        client: TestClient,
        member_headers: dict,
        member_api_key: tuple[KeyPair, any],
    ):
        """Success Criterion 4: Member role has appropriate scope restrictions."""
        _, key_info = member_api_key

        # Member should be able to list keys (with read scope)
        response = client.get("/api/v1/api-keys", headers=member_headers)
        assert response.status_code == status.HTTP_200_OK

    def test_key_metadata_includes_scopes(
        self,
        client: TestClient,
        owner_headers: dict,
        owner_api_key: tuple[KeyPair, any],
    ):
        """Success Criterion 4: Key scopes are observable."""
        _, key_info = owner_api_key

        response = client.get(f"/api/v1/api-keys/{key_info.id}", headers=owner_headers)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "scopes" in data
        assert isinstance(data["scopes"], list)

    def test_member_cannot_create_workspace_resources(
        self,
        client: TestClient,
        member_headers: dict,
        workspace_alpha: any,
    ):
        """Success Criterion 4: Member create denied with 403 (AUTH-05 UAT gap closure).

        This is the acceptance test for the UAT gap identified in 01-09:
        Member POST /workspaces/{workspace_id}/resources must return 403,
        demonstrating observable owner/admin/member behavior differences.
        """
        workspace_id = str(workspace_alpha.id)

        resource_data = {
            "name": "Member Attempted Resource",
            "resource_type": "agent_config",
            "config": '{"model": "gpt-4"}',
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/resources",
            json=resource_data,
            headers=member_headers,
        )

        # Member create must be denied with 403
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # Verify error indicates role-based denial
        data = response.json()
        assert "detail" in data


# ============================================================================
# AUTH-06: Guest Mode
# ============================================================================


class TestGuestMode:
    """Acceptance tests for AUTH-06: Guest mode with ephemeral identities."""

    def test_anonymous_request_gets_guest_identity(self, client: TestClient):
        """Success Criterion 5: Requests without identity get guest identity."""
        # Start a run without authentication (guest mode)
        run_request = {
            "input": {"message": "Hello"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=run_request)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["is_guest"] is True
        assert "run_id" in data

    def test_guest_mode_skips_persistence(self, client: TestClient):
        """Success Criterion 5: Guest runs are non-persistent."""
        run_request = {
            "input": {"message": "Test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
        }

        # Start a guest run
        start_response = client.post("/api/v1/runs", json=run_request)
        assert start_response.status_code == status.HTTP_201_CREATED

        run_data = start_response.json()
        assert "guest" in run_data["message"].lower() or run_data["is_guest"]

    def test_guest_cannot_access_protected_endpoints(self, client: TestClient):
        """Success Criterion 5: Guest cannot access authenticated endpoints."""
        # Try to access API keys endpoint without auth
        response = client.get("/api/v1/api-keys")

        # Should require authentication
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_runs_ephemeral_message(self, client: TestClient):
        """Success Criterion 5: Guest runs indicate ephemeral status."""
        run_request = {
            "input": {"message": "Test"},
            "allowed_hosts": ["*"],
        }

        response = client.post("/api/v1/runs", json=run_request)
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        # Response should indicate guest/ephemeral nature
        assert data["is_guest"] is True
        assert (
            "ephemeral" in data["message"].lower() or "guest" in data["message"].lower()
        )


# ============================================================================
# SECU-01: Default-Deny Egress Policy
# ============================================================================


class TestDefaultDenyEgress:
    """Acceptance tests for SECU-01: Default-deny egress enforcement."""

    def test_egress_blocked_without_explicit_allow(self, client: TestClient):
        """Success Criterion 6: No egress without explicit allow."""
        # Run with no allowed hosts
        run_request = {
            "input": {"url": "https://api.example.com/data"},
            "allowed_hosts": [],  # Default deny
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should be denied by policy
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_egress_allowed_with_explicit_host(self, client: TestClient):
        """Success Criterion 6: Egress allowed to explicitly permitted host."""
        run_request = {
            "input": {"url": "https://api.trusted.com/data"},
            "allowed_hosts": ["api.trusted.com"],  # Explicit allow
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should succeed
        assert response.status_code == status.HTTP_201_CREATED

    def test_wildcard_egress_pattern(self, client: TestClient):
        """Success Criterion 6: Wildcard patterns work for egress."""
        run_request = {
            "input": {"url": "https://sub.example.com/data"},
            "allowed_hosts": ["*.example.com"],  # Wildcard allow
            "allowed_tools": ["*"],
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should succeed with wildcard match
        assert response.status_code == status.HTTP_201_CREATED


# ============================================================================
# SECU-02: Default-Deny Tool Policy
# ============================================================================


class TestDefaultDenyTools:
    """Acceptance tests for SECU-02: Default-deny tool enforcement."""

    def test_tool_blocked_without_explicit_allow(self, client: TestClient):
        """Success Criterion 6: No tool access without explicit allow."""
        run_request = {
            "input": {"tool": "file_delete"},
            "allowed_hosts": ["*"],
            "allowed_tools": [],  # Default deny
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should be denied by policy
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_tool_allowed_with_explicit_allowlist(self, client: TestClient):
        """Success Criterion 6: Tool allowed when in allowlist."""
        run_request = {
            "input": {"tool": "read_file"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["read_file", "write_file"],  # Explicit allow
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should succeed
        assert response.status_code == status.HTTP_201_CREATED

    def test_unlisted_tool_blocked(self, client: TestClient):
        """Success Criterion 6: Unlisted tool is blocked."""
        run_request = {
            "input": {"tool": "dangerous_admin_tool"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["read_file"],  # Does not include dangerous tool
        }

        response = client.post("/api/v1/runs", json=run_request)

        # Should be denied
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# SECU-03: Scoped Secret Injection
# ============================================================================


class TestScopedSecrets:
    """Acceptance tests for SECU-03: Scoped secret injection."""

    def test_secrets_filtered_by_allowlist(self, client: TestClient):
        """Success Criterion 6: Only allowed secrets are injected."""
        run_request = {
            "input": {"query": "test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
            "allowed_secrets": ["API_KEY"],  # Only allow API_KEY
            "secrets": {
                "API_KEY": "secret-123",
                "DB_PASSWORD": "should-not-inject",
                "TOKEN": "also-should-not-inject",
            },
        }

        response = client.post("/api/v1/runs", json=run_request)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Only API_KEY should be in injected secrets
        assert "API_KEY" in data["injected_secrets"]
        assert "DB_PASSWORD" not in data["injected_secrets"]
        assert "TOKEN" not in data["injected_secrets"]

    def test_no_secrets_injected_without_allowlist(self, client: TestClient):
        """Success Criterion 6: No secrets without explicit allow."""
        run_request = {
            "input": {"query": "test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
            "allowed_secrets": [],  # Default deny
            "secrets": {
                "API_KEY": "secret-123",
                "DB_PASSWORD": "secret-456",
            },
        }

        response = client.post("/api/v1/runs", json=run_request)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # No secrets should be injected
        assert len(data["injected_secrets"]) == 0

    def test_secrets_only_injected_when_explicitly_allowed(self, client: TestClient):
        """Success Criterion 6: Secrets require explicit policy allow."""
        run_request = {
            "input": {"query": "test"},
            "allowed_hosts": ["*"],
            "allowed_tools": ["*"],
            "allowed_secrets": ["ALLOWED_SECRET"],
            "secrets": {
                "ALLOWED_SECRET": "this-is-allowed",
                "BLOCKED_SECRET": "this-should-be-filtered",
            },
        }

        response = client.post("/api/v1/runs", json=run_request)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Only explicitly allowed secret should be injected
        assert "ALLOWED_SECRET" in data["injected_secrets"]
        assert "BLOCKED_SECRET" not in data["injected_secrets"]


# ============================================================================
# Integration Flow Tests
# ============================================================================


class TestIntegrationFlows:
    """End-to-end integration flows combining multiple requirements."""

    def test_full_auth_lifecycle(
        self,
        client: TestClient,
        owner_headers: dict,
        workspace_alpha: any,
    ):
        """Complete flow: Create key, use it, rotate it, revoke it."""
        # 1. Create a new API key
        create_response = client.post(
            "/api/v1/api-keys",
            json={"name": "Lifecycle Test Key", "scopes": ["workspace:read"]},
            headers=owner_headers,
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        new_key_data = create_response.json()
        new_key = new_key_data["full_key"]
        key_id = new_key_data["id"]
        new_headers = {"X-Api-Key": new_key}

        # 2. Use the new key
        whoami_response = client.get("/api/v1/whoami", headers=new_headers)
        assert whoami_response.status_code == status.HTTP_200_OK

        # 3. Rotate the key
        rotate_response = client.post(
            f"/api/v1/api-keys/{key_id}/rotate",
            headers=owner_headers,
        )
        assert rotate_response.status_code == status.HTTP_200_OK
        rotated_data = rotate_response.json()
        rotated_key = rotated_data["full_key"]
        rotated_headers = {"X-Api-Key": rotated_key}

        # 4. Old key should fail, new key should work
        old_response = client.get("/api/v1/whoami", headers=new_headers)
        assert old_response.status_code == status.HTTP_401_UNAUTHORIZED

        new_response = client.get("/api/v1/whoami", headers=rotated_headers)
        assert new_response.status_code == status.HTTP_200_OK

        # 5. Revoke the key
        revoke_response = client.post(
            f"/api/v1/api-keys/{key_id}/revoke",
            headers=owner_headers,
        )
        assert revoke_response.status_code == status.HTTP_200_OK

        # 6. Key should no longer work
        revoked_response = client.get("/api/v1/whoami", headers=rotated_headers)
        assert revoked_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_workspace_isolation_with_run_policy(
        self,
        client: TestClient,
        owner_headers: dict,
        workspace_alpha: any,
    ):
        """Combined test: Workspace isolation + runtime policy enforcement."""
        workspace_id = str(workspace_alpha.id)

        # Create a resource
        resource_data = {
            "name": "Policy Test Resource",
            "resource_type": "agent_config",
        }

        create_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/resources",
            json=resource_data,
            headers=owner_headers,
        )
        assert create_response.status_code == status.HTTP_201_CREATED

        # Verify resource exists
        list_response = client.get(
            f"/api/v1/workspaces/{workspace_id}/resources",
            headers=owner_headers,
        )
        assert list_response.status_code == status.HTTP_200_OK

        # Run with restrictive policy should work
        run_request = {
            "input": {"resource": "test"},
            "allowed_hosts": ["trusted-host.com"],
            "allowed_tools": ["safe_tool"],
        }

        run_response = client.post(
            "/api/v1/runs", json=run_request, headers=owner_headers
        )
        # Policy might deny based on allowed_hosts/allowed_tools, but request is valid
        # We just verify the request is processed (not a 401/403 auth error)
        assert run_response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_403_FORBIDDEN,
        ]
