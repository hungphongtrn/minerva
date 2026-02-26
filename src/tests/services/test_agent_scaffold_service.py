"""Tests for agent scaffold service.

Covers:
- Safe generation of scaffold files
- Path traversal protection
- Idempotent behavior
- Error handling
"""

import tempfile
from pathlib import Path
import pytest

from src.services.agent_scaffold_service import (
    AgentScaffoldService,
    ScaffoldEntryType,
    ScaffoldError,
    PathTraversalError,
)


class TestAgentScaffoldService:
    """Test suite for AgentScaffoldService."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def service(self, temp_dir):
        """Create scaffold service with temp base path."""
        return AgentScaffoldService(base_path=temp_dir)

    def test_generate_creates_all_required_files_and_directories(
        self, service, temp_dir
    ):
        """Test that generate creates all required scaffold entries."""
        pack_path = "test_pack"

        results = service.generate(pack_path)

        # Should have results for directory + 3 files + 1 subdirectory
        assert len(results) == 5  # pack dir + skills dir + 3 files

        # Verify all required files exist
        pack_full_path = temp_dir / pack_path
        assert (pack_full_path / "AGENT.md").exists()
        assert (pack_full_path / "SOUL.md").exists()
        assert (pack_full_path / "IDENTITY.md").exists()
        assert (pack_full_path / "skills").exists()
        assert (pack_full_path / "skills").is_dir()

    def test_generate_is_idempotent_by_default(self, service, temp_dir):
        """Test that re-running generate doesn't corrupt existing files."""
        pack_path = "test_pack"

        # First generation
        service.generate(pack_path)

        # Read content after first generation
        pack_full_path = temp_dir / pack_path
        (pack_full_path / "AGENT.md").read_text()

        # Add custom content to one file
        custom_content = "# Custom Content\n\nThis should be preserved."
        (pack_full_path / "AGENT.md").write_text(custom_content)

        # Second generation (idempotent - should not overwrite)
        results2 = service.generate(pack_path)

        # Verify content was preserved
        agent_content_2 = (pack_full_path / "AGENT.md").read_text()
        assert agent_content_2 == custom_content

        # Verify already_existed flags
        agent_entry = [r for r in results2 if r.path.endswith("AGENT.md")][0]
        assert agent_entry.already_existed is True
        assert agent_entry.created is False

    def test_generate_with_overwrite_replaces_files(self, service, temp_dir):
        """Test that overwrite=True replaces existing files."""
        pack_path = "test_pack"

        # First generation
        service.generate(pack_path)

        # Modify a file
        pack_full_path = temp_dir / pack_path
        custom_content = "# Custom Content"
        (pack_full_path / "AGENT.md").write_text(custom_content)

        # Second generation with overwrite
        service.generate(pack_path, overwrite=True)

        # Verify content was replaced with template
        agent_content = (pack_full_path / "AGENT.md").read_text()
        assert "Agent Definition" in agent_content  # Template content
        assert agent_content != custom_content

    def test_generate_creates_nested_directories(self, service, temp_dir):
        """Test that generate handles nested pack paths."""
        pack_path = "nested/deep/pack"

        service.generate(pack_path)

        pack_full_path = temp_dir / pack_path
        assert pack_full_path.exists()
        assert (pack_full_path / "AGENT.md").exists()
        assert (pack_full_path / "skills").exists()

    def test_generate_with_absolute_path(self, service, temp_dir):
        """Test that generate works with absolute paths under base."""
        pack_path = str(temp_dir / "absolute_pack")

        service.generate(pack_path)

        assert (temp_dir / "absolute_pack" / "AGENT.md").exists()

    def test_generate_blocks_path_traversal(self, service, temp_dir):
        """Test that path traversal attacks are blocked."""
        # Attempt to escape temp_dir
        pack_path = "../outside"

        with pytest.raises(PathTraversalError) as exc_info:
            service.generate(pack_path)

        assert "escape" in str(exc_info.value).lower()

        # Verify no files were created outside
        outside_path = temp_dir.parent / "outside"
        assert not outside_path.exists()

    def test_generate_blocks_absolute_traversal(self, service, temp_dir):
        """Test that absolute paths outside base are blocked."""
        # Use system's root or temp parent
        outside_path = "/etc/passwd_pack"

        with pytest.raises(PathTraversalError):
            service.generate(outside_path)

    def test_generate_empty_path_raises_error(self, service):
        """Test that empty path raises ScaffoldError."""
        with pytest.raises(ScaffoldError):
            service.generate("")

        with pytest.raises(ScaffoldError):
            service.generate("   ")

    def test_validate_exists_returns_true_for_complete_scaffold(
        self, service, temp_dir
    ):
        """Test validate_exists returns True when all entries exist."""
        pack_path = "test_pack"
        service.generate(pack_path)

        assert service.validate_exists(pack_path) is True

    def test_validate_exists_returns_false_for_incomplete_scaffold(
        self, service, temp_dir
    ):
        """Test validate_exists returns False when entries are missing."""
        pack_path = "test_pack"

        # Create partial structure manually
        pack_full_path = temp_dir / pack_path
        pack_full_path.mkdir()
        (pack_full_path / "AGENT.md").write_text("test")
        # Missing SOUL.md, IDENTITY.md, skills/

        assert service.validate_exists(pack_path) is False

    def test_validate_exists_returns_false_for_nonexistent_path(self, service):
        """Test validate_exists returns False for non-existent paths."""
        assert service.validate_exists("nonexistent") is False

    def test_validate_exists_returns_false_for_traversal_attempt(self, service):
        """Test validate_exists returns False for invalid paths."""
        assert service.validate_exists("../etc") is False

    def test_get_missing_entries_returns_all_for_empty_directory(
        self, service, temp_dir
    ):
        """Test get_missing_entries returns all requirements for empty dir."""
        pack_path = "empty_pack"
        (temp_dir / pack_path).mkdir()

        missing = service.get_missing_entries(pack_path)

        assert "AGENT.md" in missing
        assert "SOUL.md" in missing
        assert "IDENTITY.md" in missing
        assert "skills" in missing

    def test_get_missing_entries_returns_empty_for_complete_scaffold(
        self, service, temp_dir
    ):
        """Test get_missing_entries returns empty list for complete scaffold."""
        pack_path = "test_pack"
        service.generate(pack_path)

        missing = service.get_missing_entries(pack_path)

        assert missing == []

    def test_get_missing_entries_returns_missing_items_only(self, service, temp_dir):
        """Test get_missing_entries returns only missing items."""
        pack_path = "test_pack"
        pack_full_path = temp_dir / pack_path
        pack_full_path.mkdir()

        # Create only some files
        (pack_full_path / "AGENT.md").write_text("test")
        (pack_full_path / "skills").mkdir()

        missing = service.get_missing_entries(pack_path)

        assert "AGENT.md" not in missing
        assert "skills" not in missing
        assert "SOUL.md" in missing
        assert "IDENTITY.md" in missing

    def test_get_missing_entries_for_nonexistent_path(self, service):
        """Test get_missing_entries returns all items for nonexistent path."""
        missing = service.get_missing_entries("nonexistent")

        assert len(missing) == 4  # 3 files + 1 directory

    def test_generated_files_have_content(self, service, temp_dir):
        """Test that generated files have meaningful template content."""
        pack_path = "test_pack"
        service.generate(pack_path)

        pack_full_path = temp_dir / pack_path

        # Check AGENT.md content
        agent_content = (pack_full_path / "AGENT.md").read_text()
        assert "Agent Definition" in agent_content
        assert "Purpose" in agent_content

        # Check SOUL.md content
        soul_content = (pack_full_path / "SOUL.md").read_text()
        assert "Personality" in soul_content
        assert "Values" in soul_content

        # Check IDENTITY.md content
        identity_content = (pack_full_path / "IDENTITY.md").read_text()
        assert "Metadata" in identity_content
        assert "Runtime Configuration" in identity_content

    def test_results_mark_directory_creation_correctly(self, service, temp_dir):
        """Test that results correctly mark directory creation status."""
        pack_path = "test_pack"

        results = service.generate(pack_path)

        # Find pack directory entry
        pack_entry = [r for r in results if r.path.endswith("test_pack")][0]
        assert pack_entry.entry_type == ScaffoldEntryType.DIRECTORY
        assert pack_entry.created is True
        assert pack_entry.already_existed is False

        # Find skills directory entry
        skills_entry = [r for r in results if r.path.endswith("skills")][0]
        assert skills_entry.entry_type == ScaffoldEntryType.DIRECTORY
        assert skills_entry.created is True
        assert skills_entry.already_existed is False

    def test_results_mark_file_creation_correctly(self, service, temp_dir):
        """Test that results correctly mark file creation status."""
        pack_path = "test_pack"

        results = service.generate(pack_path)

        # Find AGENT.md entry
        agent_entry = [r for r in results if r.path.endswith("AGENT.md")][0]
        assert agent_entry.entry_type == ScaffoldEntryType.FILE
        assert agent_entry.created is True
        assert agent_entry.already_existed is False

    def test_results_mark_existing_entries_on_rerun(self, service, temp_dir):
        """Test that rerun correctly marks existing entries."""
        pack_path = "test_pack"

        # First run
        service.generate(pack_path)

        # Second run
        results = service.generate(pack_path)

        # All entries should be marked as already existed
        for entry in results:
            assert entry.already_existed is True
            assert entry.created is False
