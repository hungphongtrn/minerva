"""Tests for agent pack validation service.

Covers:
- Checklist generation with proper codes/paths/messages/severity
- Source digest computation for change detection
- Deterministic output
- Error and warning classification
"""

import tempfile
from pathlib import Path

import pytest

from src.services.agent_pack_validation import (
    AgentPackValidationService,
    ValidationCode,
    ValidationSeverity,
)


class TestAgentPackValidationService:
    """Test suite for AgentPackValidationService."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def service(self):
        """Create validation service."""
        return AgentPackValidationService()

    def test_validate_complete_pack_returns_valid(self, service, temp_dir):
        """Test that a complete pack passes validation."""
        # Create complete pack structure
        pack_path = temp_dir / "complete_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent Definition")
        (pack_path / "SOUL.md").write_text("# Agent Soul")
        (pack_path / "IDENTITY.md").write_text("# Agent Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path))

        assert report.is_valid is True
        assert report.error_count == 0
        assert report.source_digest is not None

    def test_validate_missing_file_returns_error(self, service, temp_dir):
        """Test that missing required file returns error checklist entry."""
        pack_path = temp_dir / "incomplete_pack"
        pack_path.mkdir()
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()
        # Missing AGENT.md

        report = service.validate(str(pack_path))

        assert report.is_valid is False
        assert report.error_count == 1

        # Find the missing file error
        missing_entry = None
        for entry in report.checklist:
            if entry.code == ValidationCode.MISSING_FILE.value and entry.path == "AGENT.md":
                missing_entry = entry
                break

        assert missing_entry is not None
        assert missing_entry.severity == ValidationSeverity.ERROR.value
        assert "AGENT.md" in missing_entry.message

    def test_validate_missing_directory_returns_error(self, service, temp_dir):
        """Test that missing required directory returns error checklist entry."""
        pack_path = temp_dir / "incomplete_pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        # Missing skills/

        report = service.validate(str(pack_path))

        assert report.is_valid is False

        # Find the missing directory error
        missing_entry = None
        for entry in report.checklist:
            if entry.code == ValidationCode.MISSING_DIRECTORY.value and entry.path == "skills":
                missing_entry = entry
                break

        assert missing_entry is not None
        assert missing_entry.severity == ValidationSeverity.ERROR.value

    def test_validate_empty_file_returns_warning(self, service, temp_dir):
        """Test that empty file returns warning."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("")  # Empty
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path))

        # Should still be valid (empty file is a warning, not error)
        assert report.is_valid is True
        assert report.warning_count == 1

        # Find the empty file warning
        empty_entry = None
        for entry in report.checklist:
            if entry.code == ValidationCode.EMPTY_FILE.value:
                empty_entry = entry
                break

        assert empty_entry is not None
        assert empty_entry.severity == ValidationSeverity.WARNING.value

    def test_validate_nonexistent_path_returns_error(self, service, temp_dir):
        """Test that non-existent path returns error."""
        pack_path = temp_dir / "does_not_exist"

        report = service.validate(str(pack_path))

        assert report.is_valid is False
        assert report.error_count == 1
        assert report.checklist[0].code == ValidationCode.PATH_NOT_FOUND.value

    def test_validate_file_instead_of_directory_returns_error(self, service, temp_dir):
        """Test that file instead of directory returns error."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").write_text("not a directory")  # File instead of dir

        report = service.validate(str(pack_path))

        assert report.is_valid is False

        missing_entry = None
        for entry in report.checklist:
            if entry.path == "skills" and entry.severity == ValidationSeverity.ERROR.value:
                missing_entry = entry
                break

        assert missing_entry is not None

    def test_checklist_has_deterministic_format(self, service, temp_dir):
        """Test that checklist entries have required fields."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        # Create incomplete structure to get errors

        report = service.validate(str(pack_path))

        for entry in report.checklist:
            assert isinstance(entry.code, str)
            assert isinstance(entry.path, str)
            assert isinstance(entry.message, str)
            assert isinstance(entry.severity, str)
            assert entry.code != ""
            assert entry.severity in [s.value for s in ValidationSeverity]

    def test_compute_digest_is_deterministic(self, service, temp_dir):
        """Test that digest computation is deterministic."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        digest1 = service.compute_digest(str(pack_path))
        digest2 = service.compute_digest(str(pack_path))

        assert digest1 == digest2
        assert digest1 is not None
        assert len(digest1) == 64  # SHA-256 hex is 64 chars

    def test_compute_digest_changes_with_content(self, service, temp_dir):
        """Test that digest changes when content changes."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent v1")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        digest1 = service.compute_digest(str(pack_path))

        # Modify content
        (pack_path / "AGENT.md").write_text("# Agent v2")

        digest2 = service.compute_digest(str(pack_path))

        assert digest1 != digest2

    def test_compute_digest_same_for_same_content(self, service, temp_dir):
        """Test that identical content produces identical digest."""
        pack1_path = temp_dir / "pack1"
        pack2_path = temp_dir / "pack2"

        # Create identical packs
        for pack_path in [pack1_path, pack2_path]:
            pack_path.mkdir()
            (pack_path / "AGENT.md").write_text("# Same Content")
            (pack_path / "SOUL.md").write_text("# Soul")
            (pack_path / "IDENTITY.md").write_text("# Identity")
            (pack_path / "skills").mkdir()

        digest1 = service.compute_digest(str(pack1_path))
        digest2 = service.compute_digest(str(pack2_path))

        assert digest1 == digest2

    def test_check_stale_detects_changes(self, service, temp_dir):
        """Test that check_stale detects content changes."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        stored_digest = service.compute_digest(str(pack_path))

        # Not stale immediately after storing
        assert service.check_stale(str(pack_path), stored_digest) is False

        # Modify content
        (pack_path / "AGENT.md").write_text("# Modified Agent")

        # Now should be stale
        assert service.check_stale(str(pack_path), stored_digest) is True

    def test_check_stale_handles_invalid_path(self, service, temp_dir):
        """Test that check_stale handles invalid paths gracefully."""
        pack_path = temp_dir / "does_not_exist"

        # Should not raise, just return False (can't determine stale)
        result = service.check_stale(str(pack_path), "some_digest")
        assert result is False

    def test_quick_check_returns_true_for_valid_pack(self, service, temp_dir):
        """Test that quick_check returns True for valid pack."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        assert service.quick_check(str(pack_path)) is True

    def test_quick_check_returns_false_for_invalid_pack(self, service, temp_dir):
        """Test that quick_check returns False for invalid pack."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        # Incomplete structure

        assert service.quick_check(str(pack_path)) is False

    def test_quick_check_returns_false_for_nonexistent(self, service, temp_dir):
        """Test that quick_check returns False for non-existent path."""
        pack_path = temp_dir / "does_not_exist"

        assert service.quick_check(str(pack_path)) is False

    def test_get_required_entries_returns_all_requirements(self, service):
        """Test that get_required_entries returns expected structure."""
        entries = service.get_required_entries()

        assert "files" in entries
        assert "directories" in entries
        assert "AGENT.md" in entries["files"]
        assert "SOUL.md" in entries["files"]
        assert "IDENTITY.md" in entries["files"]
        assert "skills" in entries["directories"]

    def test_validate_includes_digest_for_valid_pack(self, service, temp_dir):
        """Test that validation includes digest for valid pack."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path))

        assert report.source_digest is not None
        assert len(report.source_digest) == 64

    def test_validate_no_digest_for_invalid_path(self, service, temp_dir):
        """Test that validation returns None digest for invalid path."""
        pack_path = temp_dir / "does_not_exist"

        report = service.validate(str(pack_path))

        assert report.source_digest is None

    def test_report_to_json_serializes_correctly(self, service, temp_dir):
        """Test that report can be serialized to JSON."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path))
        json_str = report.to_json()

        assert isinstance(json_str, str)
        assert "is_valid" in json_str
        assert "checklist" in json_str
        assert "source_digest" in json_str

    def test_report_to_dict_serializes_correctly(self, service, temp_dir):
        """Test that report can be converted to dict."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path))
        data = report.to_dict()

        assert isinstance(data, dict)
        assert "is_valid" in data
        assert "checklist" in data
        assert isinstance(data["checklist"], list)
        assert "source_digest" in data
        assert "error_count" in data
        assert "warning_count" in data

    def test_compute_digest_with_nested_files(self, service, temp_dir):
        """Test that digest includes nested file content."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()
        (pack_path / "skills" / "skill1.py").write_text("# Skill 1")
        (pack_path / "skills" / "skill2.py").write_text("# Skill 2")

        digest1 = service.compute_digest(str(pack_path))

        # Modify nested file
        (pack_path / "skills" / "skill1.py").write_text("# Modified Skill 1")

        digest2 = service.compute_digest(str(pack_path))

        assert digest1 != digest2

    def test_compute_digest_respects_max_file_size(self, temp_dir):
        """Test that digest respects max file size limit."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        # Create large file
        large_content = "x" * (2 * 1024 * 1024)  # 2 MB
        (pack_path / "large_file.txt").write_text(large_content)

        # Service with 1MB limit
        service_limited = AgentPackValidationService(max_file_size=1024 * 1024)

        digest = service_limited.compute_digest(str(pack_path))
        assert digest is not None
        assert len(digest) == 64

    def test_validate_without_digest_computation(self, service, temp_dir):
        """Test that validate can skip digest computation."""
        pack_path = temp_dir / "pack"
        pack_path.mkdir()
        (pack_path / "AGENT.md").write_text("# Agent")
        (pack_path / "SOUL.md").write_text("# Soul")
        (pack_path / "IDENTITY.md").write_text("# Identity")
        (pack_path / "skills").mkdir()

        report = service.validate(str(pack_path), compute_digest=False)

        assert report.is_valid is True
        assert report.source_digest is None
