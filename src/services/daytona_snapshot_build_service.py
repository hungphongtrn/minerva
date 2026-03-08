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
import re
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
        self.repo_url = repo_url or settings.PICOCLAW_REPO_URL
        self.repo_ref = repo_ref or settings.PICOCLAW_REPO_REF
        self.snapshot_name = snapshot_name or settings.DAYTONA_PICOCLAW_SNAPSHOT_NAME

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

        Args:
            repo_dir: Path to cloned repository

        Returns:
            Daytona Image configured from the Dockerfile
        """
        dockerfile_candidates = [
            repo_dir / "picoclaw" / "Dockerfile",
            repo_dir / "Dockerfile",
            repo_dir / "docker" / "Dockerfile",
        ]
        dockerfile_path = next(
            (candidate for candidate in dockerfile_candidates if candidate.exists()),
            None,
        )

        if dockerfile_path is None:
            raise SnapshotBuildError(
                "Dockerfile not found in picoclaw/, root, or docker/ directory "
                f"of {self.repo_url}",
                remediation="Ensure PICOCLAW_REPO_URL points to a valid Picoclaw repository with a Dockerfile",
            )

        # Daytona builder infers build context from Dockerfile parent directory.
        # Repositories that keep Dockerfile under `docker/` but COPY files from
        # repo root (for example `COPY go.mod go.sum ./`) fail if context stays
        # under `docker/`. Relocate Dockerfile into repo root to preserve COPY
        # semantics in those layouts.
        effective_dockerfile_path = dockerfile_path
        if (
            dockerfile_path.parent.name == "docker"
            and (repo_dir / "go.mod").exists()
            and not (dockerfile_path.parent / "go.mod").exists()
        ):
            relocated_path = repo_dir / ".daytona-builder.Dockerfile"
            relocated_path.write_text(
                dockerfile_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            effective_dockerfile_path = relocated_path

        self._normalize_dockerfile_for_builder(effective_dockerfile_path)
        self._ensure_rust_toolchain_file(repo_dir, effective_dockerfile_path)

        # Use repository Dockerfile path as-is to preserve monorepo-relative
        # COPY/ADD semantics and avoid accidental path breakage.
        image = Image.from_dockerfile(str(effective_dockerfile_path))

        return image

    def _ensure_rust_toolchain_file(
        self, repo_dir: Path, dockerfile_path: Path
    ) -> None:
        """Synthesize rust-toolchain.toml when Dockerfile expects it.

        Some runtime repos copy `rust-toolchain.toml` in Dockerfile but only
        declare Rust version in Cargo.toml. For those repos, create a minimal
        toolchain file in build context so snapshot builds remain deterministic.
        """
        try:
            dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        except OSError:
            return

        if "rust-toolchain.toml" not in dockerfile_text:
            return

        build_context = dockerfile_path.parent
        toolchain_path = build_context / "rust-toolchain.toml"
        if toolchain_path.exists():
            return

        cargo_candidates = [build_context / "Cargo.toml", repo_dir / "Cargo.toml"]
        cargo_text = ""
        for candidate in cargo_candidates:
            if candidate.exists():
                try:
                    cargo_text = candidate.read_text(encoding="utf-8")
                    break
                except OSError:
                    continue

        channel = "stable"
        match = re.search(
            r"^\s*rust-version\s*=\s*\"([^\"]+)\"", cargo_text, re.MULTILINE
        )
        if match:
            channel = match.group(1).strip()

        toolchain_path.write_text(
            f'[toolchain]\nchannel = "{channel}"\n',
            encoding="utf-8",
        )

    def _normalize_dockerfile_for_builder(self, dockerfile_path: Path) -> None:
        """Remove BuildKit-only cache mounts for broader builder compatibility."""
        try:
            dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        except OSError:
            return

        if "--mount=type=cache" not in dockerfile_text:
            return

        normalized = re.sub(
            r"\s*--mount=type=cache,[^\\\n]*(?:\\\n)?",
            " ",
            dockerfile_text,
        )
        if normalized != dockerfile_text:
            dockerfile_path.write_text(normalized, encoding="utf-8")

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
                    existing_state = getattr(existing_snapshot, "state", None)
                    existing_state_val = (
                        (getattr(existing_state, "value", None) or str(existing_state))
                        .strip()
                        .lower()
                    )

                    # Snapshot exists and is active - reuse it
                    if existing_state_val == "active":
                        if on_logs:
                            on_logs(
                                f"Snapshot '{self.snapshot_name}' already exists; reusing\n"
                            )

                        return SnapshotBuildResult(
                            success=True,
                            snapshot_name=self.snapshot_name,
                            reused=True,
                        )

                    # Snapshot exists but is not reusable.
                    # If it's failed/error, best-effort delete and recreate.
                    if existing_state_val in {"error", "failed"}:
                        if on_logs:
                            on_logs(
                                f"Snapshot '{self.snapshot_name}' exists in state "
                                f"'{existing_state_val}'; deleting and rebuilding\n"
                            )
                        try:
                            await daytona.snapshot.delete(existing_snapshot)
                        except DaytonaError as delete_error:
                            return SnapshotBuildResult(
                                success=False,
                                snapshot_name=self.snapshot_name,
                                error_message=(
                                    "Failed to delete invalid existing snapshot "
                                    f"'{self.snapshot_name}': {delete_error}"
                                ),
                                remediation=(
                                    "Delete the snapshot manually in Daytona, then rerun "
                                    "`minerva snapshot build`."
                                ),
                            )
                    else:
                        return SnapshotBuildResult(
                            success=False,
                            snapshot_name=self.snapshot_name,
                            error_message=(
                                f"Snapshot '{self.snapshot_name}' exists in state "
                                f"'{existing_state_val or 'unknown'}' and cannot be reused"
                            ),
                            remediation=(
                                "Wait for the snapshot build to finish or choose a different "
                                "snapshot name."
                            ),
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
