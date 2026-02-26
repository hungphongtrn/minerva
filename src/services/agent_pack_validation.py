"""Agent pack validation service.

Provides deterministic checklist validation and source digest computation
for agent pack scaffold verification.

Checklist format: {code, path, message, severity}
Digest: Stable SHA-256 hash of pack content for change detection.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any


class ValidationSeverity(Enum):
    """Severity levels for validation checklist entries."""

    ERROR = "error"  # Blocks registration
    WARNING = "warning"  # Non-blocking issue
    INFO = "info"  # Informational


class ValidationCode(Enum):
    """Validation error/warning codes."""

    # Blocking errors
    MISSING_FILE = "missing_file"
    MISSING_DIRECTORY = "missing_directory"
    PATH_NOT_FOUND = "path_not_found"
    PATH_NOT_DIRECTORY = "path_not_directory"

    # Warnings
    EMPTY_FILE = "empty_file"
    FILE_TOO_LARGE = "file_too_large"

    # Info
    VALID_FILE = "valid_file"
    VALID_DIRECTORY = "valid_directory"


@dataclass
class ChecklistEntry:
    """Single validation checklist entry.

    Attributes:
        code: Machine-readable error/warning code
        path: Relative path within pack
        message: Human-readable description
        severity: ERROR, WARNING, or INFO
    """

    code: str
    path: str
    message: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class ValidationReport:
    """Complete validation report for an agent pack.

    Attributes:
        is_valid: True if pack passes validation (no errors)
        checklist: List of all validation entries
        source_digest: SHA-256 digest of pack content
        error_count: Number of error entries
        warning_count: Number of warning entries
    """

    is_valid: bool
    checklist: List[ChecklistEntry]
    source_digest: Optional[str]
    error_count: int
    warning_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "checklist": [e.to_dict() for e in self.checklist],
            "source_digest": self.source_digest,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class AgentPackValidationService:
    """Service for validating agent pack scaffold structure.

    Enforces Picoclaw template requirements:
    - AGENT.md: Main agent definition
    - SOUL.md: Agent personality
    - IDENTITY.md: Agent metadata
    - skills/: Skills directory

    Provides deterministic checklist output and content digest for stale detection.
    """

    # Required scaffold entries
    REQUIRED_FILES = ["AGENT.md", "SOUL.md", "IDENTITY.md"]
    REQUIRED_DIRECTORIES = ["skills"]

    # Size limits
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(self, max_file_size: Optional[int] = None):
        """Initialize validation service.

        Args:
            max_file_size: Maximum file size to include in digest (default 10MB).
        """
        self.max_file_size = max_file_size or self.MAX_FILE_SIZE_BYTES

    def validate(
        self,
        pack_path: str,
        compute_digest: bool = True,
    ) -> ValidationReport:
        """Validate agent pack scaffold and compute digest.

        Args:
            pack_path: Path to the pack directory
            compute_digest: If True, compute source content digest

        Returns:
            ValidationReport with checklist and digest
        """
        path = Path(pack_path)
        checklist: List[ChecklistEntry] = []

        # Validate path exists and is directory
        if not path.exists():
            checklist.append(
                ChecklistEntry(
                    code=ValidationCode.PATH_NOT_FOUND.value,
                    path=str(path),
                    message=f"Pack path does not exist: {pack_path}",
                    severity=ValidationSeverity.ERROR.value,
                )
            )
            return ValidationReport(
                is_valid=False,
                checklist=checklist,
                source_digest=None,
                error_count=1,
                warning_count=0,
            )

        if not path.is_dir():
            checklist.append(
                ChecklistEntry(
                    code=ValidationCode.PATH_NOT_DIRECTORY.value,
                    path=str(path),
                    message=f"Pack path is not a directory: {pack_path}",
                    severity=ValidationSeverity.ERROR.value,
                )
            )
            return ValidationReport(
                is_valid=False,
                checklist=checklist,
                source_digest=None,
                error_count=1,
                warning_count=0,
            )

        # Validate required files
        for file_name in self.REQUIRED_FILES:
            file_path = path / file_name
            if not file_path.exists():
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.MISSING_FILE.value,
                        path=file_name,
                        message=f"Required file missing: {file_name}",
                        severity=ValidationSeverity.ERROR.value,
                    )
                )
            elif file_path.stat().st_size == 0:
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.EMPTY_FILE.value,
                        path=file_name,
                        message=f"File is empty: {file_name}",
                        severity=ValidationSeverity.WARNING.value,
                    )
                )
            else:
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.VALID_FILE.value,
                        path=file_name,
                        message=f"Valid file: {file_name}",
                        severity=ValidationSeverity.INFO.value,
                    )
                )

        # Validate required directories
        for dir_name in self.REQUIRED_DIRECTORIES:
            dir_path = path / dir_name
            if not dir_path.exists():
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.MISSING_DIRECTORY.value,
                        path=dir_name,
                        message=f"Required directory missing: {dir_name}",
                        severity=ValidationSeverity.ERROR.value,
                    )
                )
            elif not dir_path.is_dir():
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.MISSING_DIRECTORY.value,
                        path=dir_name,
                        message=f"Expected directory but found file: {dir_name}",
                        severity=ValidationSeverity.ERROR.value,
                    )
                )
            else:
                checklist.append(
                    ChecklistEntry(
                        code=ValidationCode.VALID_DIRECTORY.value,
                        path=dir_name,
                        message=f"Valid directory: {dir_name}",
                        severity=ValidationSeverity.INFO.value,
                    )
                )

        # Compute digest if requested
        source_digest = None
        if compute_digest and path.exists() and path.is_dir():
            source_digest = self.compute_digest(pack_path)

        # Count errors and warnings
        error_count = sum(
            1 for e in checklist if e.severity == ValidationSeverity.ERROR.value
        )
        warning_count = sum(
            1 for e in checklist if e.severity == ValidationSeverity.WARNING.value
        )

        return ValidationReport(
            is_valid=error_count == 0,
            checklist=checklist,
            source_digest=source_digest,
            error_count=error_count,
            warning_count=warning_count,
        )

    def compute_digest(self, pack_path: str) -> Optional[str]:
        """Compute stable SHA-256 digest of pack content.

        Walks the pack directory and computes a hash based on:
        - Relative file paths (sorted for determinism)
        - File content (limited to max_file_size)
        - Directory structure

        Args:
            pack_path: Path to the pack directory

        Returns:
            Hex digest string or None if path invalid
        """
        path = Path(pack_path)

        if not path.exists() or not path.is_dir():
            return None

        hasher = hashlib.sha256()

        # Collect all files recursively, sorted for determinism
        all_files: List[Path] = []
        for root, dirs, files in os.walk(path):
            # Sort directories for consistent traversal
            dirs.sort()
            for file in sorted(files):
                file_path = Path(root) / file
                all_files.append(file_path)

        # Hash each file
        for file_path in sorted(all_files):
            # Relative path for consistent hashing across systems
            try:
                rel_path = file_path.relative_to(path)
            except ValueError:
                continue

            # Add path to hash
            hasher.update(str(rel_path).encode("utf-8"))
            hasher.update(b"\x00")  # Separator

            # Add content (with size limit)
            try:
                size = file_path.stat().st_size
                if size <= self.max_file_size:
                    with open(file_path, "rb") as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                else:
                    # For large files, hash first N bytes + size
                    hasher.update(f"SIZE:{size}".encode("utf-8"))
                    with open(file_path, "rb") as f:
                        hasher.update(f.read(self.max_file_size))
            except (OSError, IOError):
                # Skip files we can't read
                hasher.update(b"[UNREADABLE]")

            hasher.update(b"\x00")  # Separator between files

        return hasher.hexdigest()

    def check_stale(
        self,
        pack_path: str,
        stored_digest: str,
    ) -> bool:
        """Check if pack has changed compared to stored digest.

        Args:
            pack_path: Path to the pack directory
            stored_digest: Previously stored digest

        Returns:
            True if pack has changed (is stale), False otherwise
        """
        current_digest = self.compute_digest(pack_path)

        if current_digest is None:
            # Can't compute digest, treat as not stale
            return False

        return current_digest != stored_digest

    def get_required_entries(self) -> Dict[str, List[str]]:
        """Get list of required scaffold entries.

        Returns:
            Dictionary with 'files' and 'directories' keys
        """
        return {
            "files": self.REQUIRED_FILES.copy(),
            "directories": self.REQUIRED_DIRECTORIES.copy(),
        }

    def quick_check(self, pack_path: str) -> bool:
        """Quick validation without full report generation.

        Args:
            pack_path: Path to the pack directory

        Returns:
            True if pack is valid (all required entries exist)
        """
        path = Path(pack_path)

        if not path.exists() or not path.is_dir():
            return False

        # Check required files
        for file_name in self.REQUIRED_FILES:
            if not (path / file_name).exists():
                return False

        # Check required directories
        for dir_name in self.REQUIRED_DIRECTORIES:
            dir_path = path / dir_name
            if not dir_path.exists() or not dir_path.is_dir():
                return False

        return True
