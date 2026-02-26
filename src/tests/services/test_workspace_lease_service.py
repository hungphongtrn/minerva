"""Tests for workspace lease service.

Tests lease acquisition, renewal, release, and expiration recovery with
focus on concurrency behavior and fail-closed semantics.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.db.models import Base, Workspace, WorkspaceLease, User
from src.db.repositories.workspace_lease_repository import WorkspaceLeaseRepository
from src.services.workspace_lease_service import (
    WorkspaceLeaseService,
    LeaseResult,
)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email=f"test_{uuid4().hex[:8]}@example.com",
        is_active=True,
        is_guest=False,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_workspace(db_session: Session, test_user: User) -> Workspace:
    """Create a test workspace."""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug=f"test-workspace-{uuid4().hex[:8]}",
        owner_id=test_user.id,
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def lease_service(db_session: Session) -> WorkspaceLeaseService:
    """Create a lease service instance."""
    return WorkspaceLeaseService(db_session)


class TestLeaseAcquisition:
    """Tests for lease acquisition behavior."""

    def test_acquire_lease_success(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test successful lease acquisition."""
        result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )

        assert result.success is True
        assert result.result == LeaseResult.ACQUIRED
        assert result.lease is not None
        assert result.lease.workspace_id == test_workspace.id
        assert result.lease.holder_run_id == "run-001"
        assert result.lease.holder_identity == "user-001"

    def test_acquire_lease_conflict_same_workspace(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that concurrent acquisitions for same workspace result in conflict."""
        # First acquisition succeeds
        result1 = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert result1.success is True
        db_session.commit()

        # Second acquisition should conflict
        result2 = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-002",
            holder_identity="user-002",
        )

        assert result2.success is False
        assert result2.result == LeaseResult.CONFLICT
        assert result2.lease is None
        assert "active lease" in result2.message.lower()

    def test_acquire_lease_different_workspaces_no_conflict(
        self,
        db_session: Session,
        test_user: User,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that different workspaces can have leases simultaneously."""
        # Create two workspaces
        workspace1 = Workspace(
            id=uuid4(),
            name="Workspace 1",
            slug=f"workspace-1-{uuid4().hex[:8]}",
            owner_id=test_user.id,
        )
        workspace2 = Workspace(
            id=uuid4(),
            name="Workspace 2",
            slug=f"workspace-2-{uuid4().hex[:8]}",
            owner_id=test_user.id,
        )
        db_session.add_all([workspace1, workspace2])
        db_session.commit()

        # Acquire lease for workspace 1
        result1 = lease_service.acquire_lease(
            workspace_id=workspace1.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert result1.success is True
        db_session.commit()

        # Acquire lease for workspace 2 should succeed
        result2 = lease_service.acquire_lease(
            workspace_id=workspace2.id,
            holder_run_id="run-002",
            holder_identity="user-002",
        )
        assert result2.success is True

    def test_acquire_lease_custom_ttl(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test lease acquisition with custom TTL."""
        ttl = 600  # 10 minutes

        result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
            ttl_seconds=ttl,
        )

        assert result.success is True
        expected_expiry = datetime.utcnow() + timedelta(seconds=ttl)
        # Allow 5 second tolerance for test execution time
        assert abs((result.lease.expires_at - expected_expiry).total_seconds()) < 5

    def test_acquire_lease_invalid_ttl_too_low(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that TTL below minimum is rejected."""
        with pytest.raises(ValueError) as exc_info:
            lease_service.acquire_lease(
                workspace_id=test_workspace.id,
                holder_run_id="run-001",
                holder_identity="user-001",
                ttl_seconds=5,  # Below MIN_LEASE_TTL_SECONDS (10)
            )

        assert "at least" in str(exc_info.value).lower()

    def test_acquire_lease_invalid_ttl_too_high(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that TTL above maximum is rejected."""
        with pytest.raises(ValueError) as exc_info:
            lease_service.acquire_lease(
                workspace_id=test_workspace.id,
                holder_run_id="run-001",
                holder_identity="user-001",
                ttl_seconds=7200,  # Above MAX_LEASE_TTL_SECONDS (3600)
            )

        assert "at most" in str(exc_info.value).lower()


class TestLeaseExpirationRecovery:
    """Tests for expired lease recovery behavior."""

    def test_acquire_recover_expired_lease(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that expired leases are automatically recovered."""
        # Create an expired lease manually
        expired_lease = WorkspaceLease(
            id=uuid4(),
            workspace_id=test_workspace.id,
            holder_run_id="old-run",
            holder_identity="old-user",
            acquired_at=datetime.utcnow() - timedelta(minutes=10),
            expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired
            version=1,
        )
        db_session.add(expired_lease)
        db_session.commit()

        # New acquisition should recover the expired lease
        result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="new-run",
            holder_identity="new-user",
        )

        assert result.success is True
        assert result.lease is not None
        assert result.lease.holder_run_id == "new-run"
        assert result.lease.holder_identity == "new-user"
        # The old lease should be marked as released
        db_session.refresh(expired_lease)
        assert expired_lease.released_at is not None

    def test_acquire_recover_expired_lease_deterministic(
        self,
        db_session: Session,
        test_workspace: Workspace,
    ):
        """Test that expired lease recovery is deterministic under concurrent attempts."""
        # Create an expired lease
        expired_lease = WorkspaceLease(
            id=uuid4(),
            workspace_id=test_workspace.id,
            holder_run_id="old-run",
            holder_identity="old-user",
            acquired_at=datetime.utcnow() - timedelta(minutes=10),
            expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired
            version=1,
        )
        db_session.add(expired_lease)
        db_session.commit()

        # Simulate concurrent recovery attempts via repository
        # Only one should succeed
        repository = WorkspaceLeaseRepository(db_session)

        results = []
        for i in range(5):
            lease = repository.acquire_active_lease(
                workspace_id=test_workspace.id,
                holder_run_id=f"run-{i}",
                holder_identity=f"user-{i}",
                ttl_seconds=300,
            )
            results.append(lease)
            db_session.commit()

        # Exactly one should succeed
        successful = [r for r in results if r is not None]
        assert len(successful) == 1, (
            f"Expected 1 successful acquisition, got {len(successful)}"
        )


class TestLeaseRelease:
    """Tests for lease release behavior."""

    def test_release_lease_success(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test successful lease release."""
        # Acquire lease
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert acquire_result.success is True
        db_session.commit()

        # Release lease
        release_result = lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
        )

        assert release_result.success is True
        assert release_result.result == LeaseResult.RELEASED
        assert release_result.released_at is not None

        # Verify lease is no longer active
        assert not lease_service.has_active_lease(test_workspace.id)

    def test_release_lease_holder_mismatch(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that release fails with holder mismatch."""
        # Acquire lease
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert acquire_result.success is True
        db_session.commit()

        # Try to release with different holder
        release_result = lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-002",  # Different holder
            require_holder_match=True,
        )

        assert release_result.success is False
        assert release_result.result == LeaseResult.HOLDER_MISMATCH

        # Lease should still be active
        assert lease_service.has_active_lease(test_workspace.id)

    def test_release_lease_no_holder_check(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that release can bypass holder check."""
        # Acquire lease
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert acquire_result.success is True
        db_session.commit()

        # Release without holder check
        release_result = lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-002",  # Different holder
            require_holder_match=False,  # Bypass check
        )

        assert release_result.success is True
        assert release_result.result == LeaseResult.RELEASED

    def test_release_lease_not_found(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test releasing non-existent lease."""
        release_result = lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
        )

        assert release_result.success is False
        assert release_result.result == LeaseResult.NOT_FOUND


class TestLeaseRenewal:
    """Tests for lease renewal/heartbeat behavior."""

    def test_renew_lease_success(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test successful lease renewal."""
        # Acquire lease with short TTL
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
            ttl_seconds=60,
        )
        assert acquire_result.success is True
        original_expires_at = acquire_result.lease.expires_at
        db_session.commit()

        # Renew lease
        renew_result = lease_service.renew_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            ttl_seconds=300,
        )

        assert renew_result.success is True
        assert renew_result.result == LeaseResult.RENEWED
        assert renew_result.new_expires_at > original_expires_at

    def test_renew_lease_holder_mismatch(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that renewal fails with holder mismatch."""
        # Acquire lease
        acquire_result = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert acquire_result.success is True
        db_session.commit()

        # Try to renew with different holder
        renew_result = lease_service.renew_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-002",  # Different holder
        )

        assert renew_result.success is False
        assert renew_result.result == LeaseResult.HOLDER_MISMATCH

    def test_renew_expired_lease_fails(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that renewing an expired lease fails."""
        # Create an expired lease
        expired_lease = WorkspaceLease(
            id=uuid4(),
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
            acquired_at=datetime.utcnow() - timedelta(minutes=10),
            expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired
            version=1,
        )
        db_session.add(expired_lease)
        db_session.commit()

        # Try to renew expired lease
        renew_result = lease_service.renew_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
        )

        assert renew_result.success is False
        assert renew_result.result == LeaseResult.NOT_FOUND


class TestConcurrentSameWorkspaceSerialization:
    """Tests for concurrent write serialization on same workspace."""

    def test_concurrent_acquires_serialize_deterministically(
        self,
        db_session: Session,
        test_workspace: Workspace,
    ):
        """Test that concurrent acquisition attempts serialize deterministically."""
        lease_service = WorkspaceLeaseService(db_session)

        # Simulate concurrent acquisitions
        results = []
        for i in range(10):
            result = lease_service.acquire_lease(
                workspace_id=test_workspace.id,
                holder_run_id=f"concurrent-run-{i}",
                holder_identity=f"user-{i}",
            )
            results.append(result)
            # Commit each attempt to ensure visibility
            db_session.commit()

        # Exactly one should succeed
        successful = [r for r in results if r.success]
        assert len(successful) == 1, f"Expected 1 success, got {len(successful)}"

        # All others should be CONFLICT
        conflicts = [
            r for r in results if not r.success and r.result == LeaseResult.CONFLICT
        ]
        assert len(conflicts) == 9, f"Expected 9 conflicts, got {len(conflicts)}"

    def test_concurrent_after_release_allows_new_acquisition(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that releasing allows new acquisition."""
        # First acquisition
        result1 = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        assert result1.success is True
        db_session.commit()

        # Release
        lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
        )
        db_session.commit()

        # Second acquisition should succeed
        result2 = lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-002",
            holder_identity="user-002",
        )
        assert result2.success is True


class TestFailClosedBehavior:
    """Tests for fail-closed semantics."""

    def test_fail_closed_ambiguous_state(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that ambiguous lease states fail closed."""
        # This test verifies the service returns NOT_FOUND when state is unclear
        # Try to renew a lease that doesn't exist
        renew_result = lease_service.renew_lease(
            workspace_id=test_workspace.id,
            holder_run_id="non-existent-run",
        )

        assert renew_result.success is False
        assert renew_result.result == LeaseResult.NOT_FOUND

    def test_fail_closed_release_no_lease(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that releasing non-existent lease fails gracefully."""
        release_result = lease_service.release_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
        )

        assert release_result.success is False
        assert release_result.result == LeaseResult.NOT_FOUND


class TestLeaseQueries:
    """Tests for lease query operations."""

    def test_has_active_lease_true(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test checking for active lease when one exists."""
        lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        db_session.commit()

        assert lease_service.has_active_lease(test_workspace.id) is True

    def test_has_active_lease_false(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test checking for active lease when none exists."""
        assert lease_service.has_active_lease(test_workspace.id) is False

    def test_get_active_lease_returns_correct_lease(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test getting active lease returns the correct lease."""
        lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        db_session.commit()

        active_lease = lease_service.get_active_lease(test_workspace.id)
        assert active_lease is not None
        assert active_lease.holder_run_id == "run-001"

    def test_get_active_lease_none_when_expired(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test that expired leases are not returned as active."""
        # Create an expired lease
        expired_lease = WorkspaceLease(
            id=uuid4(),
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
            acquired_at=datetime.utcnow() - timedelta(minutes=10),
            expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired
            version=1,
        )
        db_session.add(expired_lease)
        db_session.commit()

        # Should not be returned as active
        active_lease = lease_service.get_active_lease(test_workspace.id)
        assert active_lease is None


class TestForceReleaseExpired:
    """Tests for administrative force release."""

    def test_force_release_expired_lease(
        self,
        db_session: Session,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test administrative force release."""
        # Acquire lease
        lease_service.acquire_lease(
            workspace_id=test_workspace.id,
            holder_run_id="run-001",
            holder_identity="user-001",
        )
        db_session.commit()

        # Force release (bypass holder check)
        result = lease_service.force_release_expired(test_workspace.id)

        assert result.success is True
        assert result.result == LeaseResult.RELEASED

        # Verify lease is released
        assert not lease_service.has_active_lease(test_workspace.id)

    def test_force_release_no_lease(
        self,
        test_workspace: Workspace,
        lease_service: WorkspaceLeaseService,
    ):
        """Test force release when no lease exists."""
        result = lease_service.force_release_expired(test_workspace.id)

        assert result.success is False
        assert result.result == LeaseResult.NOT_FOUND
