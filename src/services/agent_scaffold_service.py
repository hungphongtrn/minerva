"""Agent scaffold service for creating Picoclaw template artifacts.

Provides safe, idempotent generation of required template files:
- AGENT.md: Main agent definition and behavior
- SOUL.md: Agent personality and tone
- IDENTITY.md: Agent identity metadata
- skills/: Directory for agent skills
"""

from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class ScaffoldError(Exception):
    """Raised when scaffold generation fails."""

    pass


class PathTraversalError(ScaffoldError):
    """Raised when path traversal is detected."""

    pass


class ScaffoldEntryType(Enum):
    """Type of scaffold entry."""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass
class ScaffoldEntry:
    """Represents a scaffold entry result."""

    path: str
    entry_type: ScaffoldEntryType
    created: bool
    already_existed: bool


class AgentScaffoldService:
    """Service for generating Picoclaw agent scaffold files.

    Enforces safe path handling and idempotent generation.
    """

    # Required scaffold entries
    REQUIRED_FILES = ["AGENT.md", "SOUL.md", "IDENTITY.md"]
    REQUIRED_DIRECTORIES = ["skills"]

    # Template content for new files
    TEMPLATES = {
        "AGENT.md": """# Agent Definition

## Name
Your agent name here

## Purpose
Describe what this agent does and its primary responsibilities.

## Capabilities
- List key capabilities here
- Each capability should be actionable

## Constraints
- List any constraints or limitations
- Security boundaries, tool restrictions, etc.

## Workflow
1. Describe the agent's typical workflow
2. Step-by-step process

## Context
- Relevant context the agent needs
- References to external systems or data
""",
        "SOUL.md": """# Agent Soul

## Personality
Describe the agent's personality traits:
- Tone (professional, friendly, technical, etc.)
- Communication style
- Approach to problem-solving

## Values
- Core values that guide the agent's behavior
- Ethical boundaries and principles

## Voice Examples

### Example 1: Greeting
"Hello! I'm here to help you with..."

### Example 2: Problem Solving
"Let me analyze this step by step..."

### Example 3: Uncertainty
"I'm not certain about that. Let me clarify..."
""",
        "IDENTITY.md": """# Agent Identity

## Metadata
- **Version**: 1.0.0
- **Created**: YYYY-MM-DD
- **Author**: Your name/team

## Identity
- **Display Name**: How the agent should be referred to
- **Internal ID**: Unique identifier for this agent
- **Type**: Type/classification of agent

## Runtime Configuration
- **Model**: Default model or model family
- **Temperature**: 0.7 (adjust as needed)
- **Max Tokens**: 4000

## Dependencies
- List any external dependencies
- Required tools or services

## Secrets/Environment
- Required environment variables
- Secret keys or API credentials needed
""",
    }

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize scaffold service.

        Args:
            base_path: Optional base path for validating relative paths.
                      If not provided, current working directory is used and
                      absolute paths are allowed (for API/integration flows).
        """
        if base_path is not None:
            self.base_path = base_path
            self._base_path_explicit = True
        else:
            self.base_path = Path.cwd()
            self._base_path_explicit = False

    def generate(
        self,
        pack_path: str,
        overwrite: bool = False,
    ) -> List[ScaffoldEntry]:
        """Generate scaffold files in the specified pack path.

        Creates required files and directories for a Picoclaw agent pack.
        Safe against path traversal attacks and idempotent by default.

        Args:
            pack_path: Path to the pack directory (relative to base or absolute)
            overwrite: If True, overwrite existing files with templates.
                      If False, skip existing files (default behavior).

        Returns:
            List of ScaffoldEntry describing what was created or skipped.

        Raises:
            PathTraversalError: If pack_path attempts path traversal outside base.
            ScaffoldError: If directory creation fails or path is invalid.
        """
        # Normalize and validate path
        target_path = self._normalize_and_validate_path(pack_path)

        results: List[ScaffoldEntry] = []

        # Create the pack directory if it doesn't exist
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)
            results.append(
                ScaffoldEntry(
                    path=str(target_path),
                    entry_type=ScaffoldEntryType.DIRECTORY,
                    created=True,
                    already_existed=False,
                )
            )
        else:
            results.append(
                ScaffoldEntry(
                    path=str(target_path),
                    entry_type=ScaffoldEntryType.DIRECTORY,
                    created=False,
                    already_existed=True,
                )
            )

        # Create required directories
        for dir_name in self.REQUIRED_DIRECTORIES:
            dir_path = target_path / dir_name
            already_existed = dir_path.exists()

            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                results.append(
                    ScaffoldEntry(
                        path=str(dir_path),
                        entry_type=ScaffoldEntryType.DIRECTORY,
                        created=not already_existed,
                        already_existed=already_existed,
                    )
                )
            except OSError as e:
                raise ScaffoldError(f"Failed to create directory {dir_path}: {e}") from e

        # Create required files
        for file_name in self.REQUIRED_FILES:
            file_path = target_path / file_name
            already_existed = file_path.exists()

            if already_existed and not overwrite:
                # Idempotent: skip existing files unless overwrite requested
                results.append(
                    ScaffoldEntry(
                        path=str(file_path),
                        entry_type=ScaffoldEntryType.FILE,
                        created=False,
                        already_existed=True,
                    )
                )
                continue

            try:
                template = self.TEMPLATES.get(file_name, "")
                file_path.write_text(template, encoding="utf-8")
                results.append(
                    ScaffoldEntry(
                        path=str(file_path),
                        entry_type=ScaffoldEntryType.FILE,
                        created=True,
                        already_existed=already_existed,
                    )
                )
            except OSError as e:
                raise ScaffoldError(f"Failed to create file {file_path}: {e}") from e

        return results

    def validate_exists(self, pack_path: str) -> bool:
        """Check if scaffold structure exists at pack path.

        Args:
            pack_path: Path to the pack directory.

        Returns:
            True if all required files and directories exist.
        """
        try:
            target_path = self._normalize_and_validate_path(pack_path)
        except PathTraversalError:
            return False

        if not target_path.exists():
            return False

        # Check required files
        for file_name in self.REQUIRED_FILES:
            if not (target_path / file_name).exists():
                return False

        # Check required directories
        for dir_name in self.REQUIRED_DIRECTORIES:
            dir_path = target_path / dir_name
            if not dir_path.exists() or not dir_path.is_dir():
                return False

        return True

    def _normalize_and_validate_path(self, pack_path: str) -> Path:
        """Normalize path and validate against traversal attacks.

        Supports safe absolute paths (e.g., temp directories) while blocking
        traversal attacks that attempt to escape intended boundaries.

        Args:
            pack_path: Path to normalize and validate.

        Returns:
            Normalized absolute Path.

        Raises:
            PathTraversalError: If path attempts path traversal.
            ScaffoldError: If path is empty or invalid.
        """
        if not pack_path or not pack_path.strip():
            raise ScaffoldError("Pack path cannot be empty")

        # Convert to Path
        path = Path(pack_path)

        # Resolve to eliminate .. and symlinks
        try:
            resolved_path = path.resolve()
        except (OSError, RuntimeError) as e:
            raise ScaffoldError(f"Failed to resolve path {pack_path}: {e}") from e

        # Validate: check for traversal attacks
        # For absolute paths:
        #   - If base_path is explicit: validate containment within base_path
        #   - If base_path is default (cwd): allow safe absolute paths
        # For relative paths: always validate containment within base_path
        if path.is_absolute() and not self._base_path_explicit:
            # Absolute path with default base: validate no traversal components
            if ".." in pack_path.replace("\\", "/"):
                raise PathTraversalError(f"Path '{pack_path}' contains traversal components")
        else:
            # Either relative path, or absolute with explicit base:
            # Validate containment within base_path
            if path.is_absolute():
                path_to_validate = resolved_path
            else:
                # Relative path: resolve against base
                path_to_validate = (self.base_path / path).resolve()

            # Validate: path must be within or equal to base_path
            try:
                path_to_validate.relative_to(self.base_path.resolve())
            except ValueError:
                raise PathTraversalError(
                    f"Path '{pack_path}' attempts to escape base directory "
                    f"'{self.base_path}'. Resolved to: '{path_to_validate}'"
                )

            if not path.is_absolute():
                resolved_path = path_to_validate

        return resolved_path

    def get_missing_entries(self, pack_path: str) -> List[str]:
        """Get list of missing required scaffold entries.

        Args:
            pack_path: Path to the pack directory.

        Returns:
            List of missing entry names (files or directories).
        """
        try:
            target_path = self._normalize_and_validate_path(pack_path)
        except PathTraversalError:
            # If path is invalid, all entries are missing
            return self.REQUIRED_FILES + self.REQUIRED_DIRECTORIES

        if not target_path.exists():
            return self.REQUIRED_FILES + self.REQUIRED_DIRECTORIES

        missing: List[str] = []

        for file_name in self.REQUIRED_FILES:
            if not (target_path / file_name).exists():
                missing.append(file_name)

        for dir_name in self.REQUIRED_DIRECTORIES:
            dir_path = target_path / dir_name
            if not dir_path.exists() or not dir_path.is_dir():
                missing.append(dir_name)

        return missing
