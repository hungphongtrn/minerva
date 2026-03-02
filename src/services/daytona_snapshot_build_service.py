"""Daytona snapshot build service for Picoclaw base runtime.

Implements the `minerva snapshot build` workflow using Daytona Declarative Builder
to create a deterministic snapshot from the Picoclaw Git repository.

The service:
1. Clones the Picoclaw repo from configured URL and ref
2. Builds a Daytona Image from the Dockerfile
3. Creates a named snapshot from the image
4. Streams build logs via callback
5. Returns structured results for CLI consumption

Environment variables:
- PICOCLAW_REPO_URL: Git repository URL (required)
- PICOCLAW_REPO_REF: Branch/tag/sha (default: main)
- DAYTONA_PICOCLAW_SNAPSHOT_NAME: Target snapshot name (required)
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from daytona import AsyncDaytona, CreateSnapshotParams, DaytonaError, Image

from src.config.settings import settings


class SnapshotBuildError(Exception):
    """Raised when snapshot build fails."""

    def __init__(
        self,
        message: str,
        remediation: Optional[str] = None,
    ):
        super().__init__(message)
        self.remediation = remediation


@dataclass
class SnapshotBuildResult:
    """Result of snapshot build operation."""

    success: bool
    """Whether the build succeeded."""

    snapshot_name: str
    """Name of the created snapshot."""

    error_message: Optional[str] = None
    """Error message if build failed."""

    remediation: Optional[str] = None
    """Actionable guidance if build failed."""

    reused: bool = False
    """Whether an existing snapshot was reused instead of created."""


class DaytonaSnapshotBuildService:
    """Service for building Picoclaw base snapshot via Daytona Declarative Builder.

    This service is pure (no CLI parsing) and returns structured results
    for the command layer to consume.

    Usage:
        service = DaytonaSnapshotBuildService()

        def log_handler(chunk: str) -> None:
            print(chunk, end="")

        result = await service.build_snapshot(on_logs=log_handler)

        if result.success:
            print(f"Created snapshot: {result.snapshot_name}")
        else:
            print(f"Build failed: {result.error_message}")
    """

    def __init__(
        self,
        repo_url: Optional[str] = None,
        repo_ref: Optional[str] = None,
        snapshot_name: Optional[str] = None,
    ):
        """Initialize the snapshot build service.

        Args:
            repo_url: Git repository URL (defaults to PICOCLAW_REPO_URL env var)
            repo_ref: Git ref (branch/tag/sha, defaults to PICOCLAW_REPO_REF env var or 'main')
            snapshot_name: Target snapshot name (defaults to DAYTONA_PICOCLAW_SNAPSHOT_NAME env var)
        """
        self.repo_url = repo_url or os.getenv("PICOCLAW_REPO_URL")
        self.repo_ref = repo_ref or os.getenv("PICOCLAW_REPO_REF", "main")
        self.snapshot_name = snapshot_name or os.getenv(
            "DAYTONA_PICOCLAW_SNAPSHOT_NAME"
        )

    def _validate_config(self) -> None:
        """Validate required configuration.

        Raises:
            SnapshotBuildError: If required configuration is missing
        """
        missing = []

        if not self.repo_url:
            missing.append("PICOCLAW_REPO_URL")

        if not self.snapshot_name:
            missing.append("DAYTONA_PICOCLAW_SNAPSHOT_NAME")

        if missing:
            raise SnapshotBuildError(
                f"Missing required configuration: {', '.join(missing)}",
                remediation=f"Set {' and '.join(missing)} environment variables",
            )

    def _clone_repo(self, target_dir: Path) -> None:
        """Clone the Picoclaw repository.

        Args:
            target_dir: Directory to clone into

        Raises:
            SnapshotBuildError: If clone fails
        """
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--branch",
                    self.repo_ref,
                    "--depth",
                    "1",
                    self.repo_url,
                    str(target_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise SnapshotBuildError(
                f"Failed to clone repository: {e.stderr}",
                remediation="Verify PICOCLAW_REPO_URL and PICOCLAW_REPO_REF are correct and accessible",
            )

    def _build_image(self, repo_dir: Path) -> Image:
        """Build Daytona Image from Picoclaw Dockerfile.

        The Dockerfile is a multi-stage Go build that:
        1. Builds the picoclaw binary using golang:1.26.0-alpine
        2. Packages it into alpine:3.23 with health checks

        Since the Dockerfile is self-contained with COPY commands,
        we use Image.from_dockerfile() which handles the build context.

        Args:
            repo_dir: Path to cloned repository

        Returns:
            Daytona Image configured from the Dockerfile
        """
        dockerfile_path = repo_dir / "Dockerfile"

        if not dockerfile_path.exists():
            raise SnapshotBuildError(
                f"Dockerfile not found at {dockerfile_path}",
                remediation="Ensure PICOCLAW_REPO_URL points to a valid Picoclaw repository",
            )

        # Use from_dockerfile for self-contained Dockerfiles
        # Daytona will handle the build context automatically
        image = Image.from_dockerfile(str(dockerfile_path))

        return image

    async def build_snapshot(
        self,
        on_logs: Optional[Callable[[str], None]] = None,
    ) -> SnapshotBuildResult:
        """Build the Picoclaw base snapshot.

        This method is idempotent: if the snapshot already exists, it will be
        reused instead of creating a duplicate.

        This method:
        1. Validates configuration
        2. Checks if snapshot already exists (reuse if found)
        3. Clones the repository
        4. Builds the image from Dockerfile
        5. Creates the snapshot (if not found)

        Args:
            on_logs: Optional callback for streaming build logs

        Returns:
            SnapshotBuildResult with success status and details
        """
        try:
            # Validate configuration
            self._validate_config()

            # Check if snapshot already exists (idempotent check)
            async with AsyncDaytona() as daytona:
                try:
                    existing_snapshot = await daytona.snapshot.get(self.snapshot_name)
                    # Snapshot exists - reuse it
                    if on_logs:
                        on_logs(
                            f"Snapshot '{self.snapshot_name}' already exists; reusing\n"
                        )

                    return SnapshotBuildResult(
                        success=True,
                        snapshot_name=self.snapshot_name,
                        reused=True,
                    )
                except DaytonaError as e:
                    # Check if this is a "not found" error vs auth/permission error
                    error_str = str(e).lower()
                    is_not_found = (
                        "not found" in error_str
                        or "404" in error_str
                        or "does not exist" in error_str
                        or "no such snapshot" in error_str
                    )

                    if not is_not_found:
                        # Auth/permission error - fail closed, don't attempt create
                        error_msg = f"Failed to check snapshot: {e}"

                        # Provide remediation based on error type
                        if "write:snapshots" in error_str or "permission" in error_str:
                            remediation = (
                                "Ensure your Daytona API key has 'read:snapshots' scope. "
                                "Check your Daytona Cloud or self-hosted configuration."
                            )
                        elif "unauthorized" in error_str or "401" in error_str:
                            remediation = "Verify DAYTONA_API_KEY is set correctly"
                        else:
                            remediation = "Check Daytona logs for details"

                        if on_logs:
                            on_logs(f"\n❌ {error_msg}\n")
                            on_logs(f"Remediation: {remediation}\n")

                        return SnapshotBuildResult(
                            success=False,
                            snapshot_name=self.snapshot_name,
                            error_message=error_msg,
                            remediation=remediation,
                        )

                    # Not found - proceed to create (this is the expected path for new snapshots)
                    if on_logs:
                        on_logs(
                            f"Snapshot '{self.snapshot_name}' not found, building...\n"
                        )

            # Create temporary directory for repo clone
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_dir = Path(tmpdir) / "picoclaw"

                # Clone repository
                if on_logs:
                    on_logs(f"Cloning {self.repo_url} (ref: {self.repo_ref})...\n")

                self._clone_repo(repo_dir)

                if on_logs:
                    on_logs("Repository cloned successfully\n")
                    on_logs("Building image from Dockerfile...\n")

                # Build image from Dockerfile
                image = self._build_image(repo_dir)

                if on_logs:
                    on_logs(f"Creating snapshot '{self.snapshot_name}'...\n")

                # Create snapshot via Daytona SDK
                async with AsyncDaytona() as daytona:
                    params = CreateSnapshotParams(
                        name=self.snapshot_name,
                        image=image,
                    )

                    await daytona.snapshot.create(
                        params,
                        on_logs=on_logs,
                    )

                if on_logs:
                    on_logs(
                        f"\n✅ Snapshot '{self.snapshot_name}' created successfully\n"
                    )

                return SnapshotBuildResult(
                    success=True,
                    snapshot_name=self.snapshot_name,
                    reused=False,
                )

        except SnapshotBuildError as e:
            if on_logs:
                on_logs(f"\n❌ Build failed: {e}\n")
                if e.remediation:
                    on_logs(f"Remediation: {e.remediation}\n")

            return SnapshotBuildResult(
                success=False,
                snapshot_name=self.snapshot_name,
                error_message=str(e),
                remediation=e.remediation,
            )

        except DaytonaError as e:
            error_msg = f"Daytona API error: {e}"

            # Check for common Daytona permission errors
            error_str = str(e).lower()
            if "write:snapshots" in error_str or "permission" in error_str:
                remediation = (
                    "Ensure your Daytona API key has 'write:snapshots' scope. "
                    "Check your Daytona Cloud or self-hosted configuration."
                )
            elif "unauthorized" in error_str or "401" in error_str:
                remediation = "Verify DAYTONA_API_KEY is set correctly"
            elif "not found" in error_str or "404" in error_str:
                remediation = (
                    "Verify DAYTONA_API_URL is correct (leave empty for Daytona Cloud)"
                )
            else:
                remediation = "Check Daytona logs for details"

            if on_logs:
                on_logs(f"\n❌ {error_msg}\n")
                on_logs(f"Remediation: {remediation}\n")

            return SnapshotBuildResult(
                success=False,
                snapshot_name=self.snapshot_name,
                error_message=error_msg,
                remediation=remediation,
            )

        except Exception as e:
            error_msg = f"Unexpected error: {e}"

            if on_logs:
                on_logs(f"\n❌ {error_msg}\n")

            return SnapshotBuildResult(
                success=False,
                snapshot_name=self.snapshot_name,
                error_message=error_msg,
                remediation=None,
            )
