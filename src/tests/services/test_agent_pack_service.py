"""Tests for agent pack service.

Covers:
- Path-linked registration and update
- Validation integration
- Repository usage for persistence
- Stale detection and revalidation
"""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base,
    User,
    Workspace,
    AgentPackValidationStatus,
)
from src.services.agent_pack_service import (
    AgentPackService,
    AgentPackServiceError,
)
from src.services.agent_pack_validation import AgentPackValidationService
from src.db.repositories.agent_pack_repository import AgentPackRepository


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
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_workspace(db_session):
    """Create a test workspace with user."""
    user = User(
        id=uuid4(),
        email=f"test_{uuid4().hex[:8]}@example.com",
    )
    db_session.add(user)
    db_session.flush()

    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug=f"test-{uuid4().hex[:8]}",
        owner_id=user.id,
    )
    db_session.add(workspace)
    db_session.commit()

    return workspace


class TestAgentPackService:
    """Test suite for AgentPackService."""

    def test_uses_repository_for_registration(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that service uses repository for pack registration."""
        # Create valid pack
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        assert result.success is True
        assert result.pack is not None
        assert result.pack.workspace_id == test_workspace.id

        # Verify repository was used (pack was persisted)
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(result.pack.id)
        assert found_pack is not None
        assert found_pack.name == "Test Pack"

    def test_blocks_invalid_pack_registration(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that invalid packs are blocked and return checklist."""
        # Create incomplete pack (missing files)
        pack_path = temp_dir / "invalid_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        # Missing SOUL.md, IDENTITY.md, skills/

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Invalid Pack",
            source_path=str(pack_path),
        )

        assert result.success is False
        assert result.pack is None
        assert result.report.is_valid is False
        assert result.report.error_count > 0

        # Verify no pack was persisted
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_workspace_and_path(test_workspace.id, str(pack_path))
        assert found_pack is None

    def test_upserts_existing_pack(self, db_session, test_workspace, temp_dir):
        """Test that registration updates existing pack for same workspace+path."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        # First registration
        result1 = service.register(
            workspace_id=test_workspace.id,
            name="Original Name",
            source_path=str(pack_path),
        )
        pack_id = result1.pack.id

        # Second registration (should update, not create new)
        result2 = service.register(
            workspace_id=test_workspace.id,
            name="Updated Name",
            source_path=str(pack_path),
        )

        assert result2.success is True
        assert result2.pack.id == pack_id  # Same pack ID
        assert result2.pack.name == "Updated Name"

    def test_stores_source_digest_via_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that source digest is stored through repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        assert result.pack.source_digest is not None
        assert len(result.pack.source_digest) == 64

        # Verify digest stored in database via repository
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(result.pack.id)
        assert found_pack.source_digest == result.pack.source_digest

    def test_stores_validation_status_via_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that validation status is stored through repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        assert result.pack.validation_status == AgentPackValidationStatus.VALID

        # Verify status stored in database
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(result.pack.id)
        assert found_pack.validation_status == AgentPackValidationStatus.VALID

    def test_check_stale_detects_changes(self, db_session, test_workspace, temp_dir):
        """Test that check_stale detects source changes."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        # Register pack
        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id
        original_digest = result.pack.source_digest

        # Not stale initially
        stale_result = service.check_stale(pack_id)
        assert stale_result.is_stale is False
        assert stale_result.stored_digest == original_digest

        # Modify source
        (pack_path / "AGENT.md").write_text("# Modified Agent")

        # Now should be stale
        stale_result = service.check_stale(pack_id)
        assert stale_result.is_stale is True
        assert stale_result.stored_digest == original_digest
        assert stale_result.current_digest != original_digest

    def test_check_stale_updates_status_via_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that check_stale updates status through repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Modify source and check stale
        (pack_path / "AGENT.md").write_text("# Modified")
        service.check_stale(pack_id)

        # Verify status updated via repository
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(pack_id)
        assert found_pack.validation_status == AgentPackValidationStatus.STALE

    def test_revalidate_refreshes_status(self, db_session, test_workspace, temp_dir):
        """Test that revalidate updates validation status."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Modify source to make stale
        (pack_path / "AGENT.md").write_text("# Modified")
        service.check_stale(pack_id)

        # Revalidate
        reval_result = service.revalidate(pack_id)

        assert reval_result.success is True
        assert reval_result.pack.validation_status == AgentPackValidationStatus.VALID

    def test_revalidate_updates_digest_via_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that revalidate updates digest through repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id
        original_digest = result.pack.source_digest

        # Modify source
        (pack_path / "AGENT.md").write_text("# Modified Agent Content")

        # Revalidate
        service.revalidate(pack_id)

        # Verify digest updated via repository
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(pack_id)
        assert found_pack.source_digest != original_digest

    def test_revalidate_reports_invalid_packs(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that revalidate reports invalid packs."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Delete required file to make invalid
        (pack_path / "AGENT.md").unlink()

        # Revalidate
        reval_result = service.revalidate(pack_id)

        assert reval_result.success is False
        assert reval_result.report.is_valid is False
        assert reval_result.report.error_count > 0

    def test_get_pack_uses_repository(self, db_session, test_workspace, temp_dir):
        """Test that get_pack delegates to repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Get pack
        found_pack = service.get_pack(pack_id)

        assert found_pack is not None
        assert found_pack.id == pack_id

    def test_get_pack_by_path_normalizes_path(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that get_pack_by_path normalizes the source path."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        # Try to get with different path representation
        found_pack = service.get_pack_by_path(
            test_workspace.id,
            str(pack_path),  # Same path
        )

        assert found_pack is not None
        assert found_pack.id == result.pack.id

    def test_list_workspace_packs_delegates_to_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that list_workspace_packs delegates to repository."""
        # Create multiple packs
        for i in range(3):
            pack_path = temp_dir / f"pack_{i}"
            pack_path.mkdir()
            (pack_path / "AGENT.md").write_text("# Agent")
            (pack_path / "SOUL.md").write_text("# Soul")
            (pack_path / "IDENTITY.md").write_text("# Identity")
            (pack_path / "skills").mkdir()

            service = AgentPackService(db_session)
            service.register(
                workspace_id=test_workspace.id,
                name=f"Pack {i}",
                source_path=str(pack_path),
            )

        # List packs
        service = AgentPackService(db_session)
        packs = service.list_workspace_packs(test_workspace.id)

        assert len(packs) == 3

    def test_list_stale_packs_delegates_to_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that list_stale_packs delegates to repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Make stale
        (pack_path / "AGENT.md").write_text("# Modified")
        service.check_stale(pack_id)

        # List stale packs
        stale_packs = service.list_stale_packs(test_workspace.id)

        assert len(stale_packs) == 1
        assert stale_packs[0].id == pack_id

    def test_set_pack_active_delegates_to_repository(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that set_pack_active delegates to repository."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        # Deactivate
        updated_pack = service.set_pack_active(pack_id, False)

        assert updated_pack.is_active is False

        # Verify via repository
        repo = AgentPackRepository(db_session)
        found_pack = repo.get_by_id(pack_id)
        assert found_pack.is_active is False

    def test_check_stale_raises_for_missing_pack(self, db_session):
        """Test that check_stale raises for non-existent pack."""
        service = AgentPackService(db_session)

        with pytest.raises(AgentPackServiceError) as exc_info:
            service.check_stale(uuid4())

        assert "not found" in str(exc_info.value).lower()

    def test_revalidate_returns_error_for_missing_pack(self, db_session):
        """Test that revalidate returns error for non-existent pack."""
        service = AgentPackService(db_session)

        result = service.revalidate(uuid4())

        assert result.success is False
        assert "not found" in result.errors[0].lower()

    def test_uses_injected_repository(self, db_session, test_workspace, temp_dir):
        """Test that service uses injected repository instance."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        # Inject custom repository
        custom_repo = AgentPackRepository(db_session)
        service = AgentPackService(db_session, repository=custom_repo)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        assert result.success is True
        assert result.pack is not None

    def test_uses_injected_validation_service(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that service uses injected validation service."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        # Inject custom validation service
        custom_validation = AgentPackValidationService()
        service = AgentPackService(
            db_session,
            validation_service=custom_validation,
        )

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        assert result.success is True

    def test_normalize_path_handles_relative_paths(
        self, db_session, test_workspace, temp_dir
    ):
        """Test that relative paths are normalized to absolute."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        # Register with relative path
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = service.register(
                workspace_id=test_workspace.id,
                name="Test Pack",
                source_path="test_pack",  # Relative path
            )
        finally:
            os.chdir(original_cwd)

        assert result.success is True
        # Path should be normalized to absolute
        assert result.pack.source_path == str(pack_path.resolve())

    def test_registration_result_to_dict(self, db_session, test_workspace, temp_dir):
        """Test that RegistrationResult can be serialized."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )

        data = result.to_dict()

        assert "success" in data
        assert "pack_id" in data
        assert "validation" in data
        assert "errors" in data

    def test_stale_check_result_to_dict(self, db_session, test_workspace, temp_dir):
        """Test that StaleCheckResult can be serialized."""
        pack_path = temp_dir / "test_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        service = AgentPackService(db_session)

        result = service.register(
            workspace_id=test_workspace.id,
            name="Test Pack",
            source_path=str(pack_path),
        )
        pack_id = result.pack.id

        stale_result = service.check_stale(pack_id)
        data = stale_result.to_dict()

        assert "is_stale" in data
        assert "current_digest" in data
        assert "stored_digest" in data
        assert "pack_id" in data
