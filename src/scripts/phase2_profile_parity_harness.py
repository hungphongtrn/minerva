#!/usr/bin/env python3
"""Phase 2 Profile Parity Harness.

Automated cross-profile parity verification for local_compose and daytona profiles.
Executes the same routing scenarios under both profiles and verifies equivalent
semantic outcomes without manual profile rewiring.

Usage:
    # CI mode: Run both profiles sequentially with pass/fail exit code
    uv run python src/scripts/phase2_profile_parity_harness.py --mode ci

    # Local mode: Run specific profile with verbose output
    uv run python src/scripts/phase2_profile_parity_harness.py --mode local --profile local_compose

    # Verbose mode: Show all test output
    uv run python src/scripts/phase2_profile_parity_harness.py --mode ci --verbose

Environment:
    SANDBOX_PROFILE: Overrides --profile flag when set
    DAYTONA_API_KEY: Required for daytona profile
    DAYTONA_API_URL: Optional for self-hosted Daytona
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ProfileResult:
    """Result of running tests under a specific profile."""

    profile: str
    success: bool
    tests_passed: int = 0
    tests_failed: int = 0
    errors: List[str] = field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0


@dataclass
class ParityReport:
    """Complete parity report across all profiles."""

    local_result: Optional[ProfileResult] = None
    daytona_result: Optional[ProfileResult] = None
    parity_check_passed: bool = False
    overall_success: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "overall_success": self.overall_success,
            "parity_check_passed": self.parity_check_passed,
            "profiles": {
                "local_compose": (
                    {
                        "success": self.local_result.success,
                        "tests_passed": self.local_result.tests_passed,
                        "tests_failed": self.local_result.tests_failed,
                        "duration_seconds": self.local_result.duration_seconds,
                        "errors": self.local_result.errors,
                    }
                    if self.local_result
                    else None
                ),
                "daytona": (
                    {
                        "success": self.daytona_result.success,
                        "tests_passed": self.daytona_result.tests_passed,
                        "tests_failed": self.daytona_result.tests_failed,
                        "duration_seconds": self.daytona_result.duration_seconds,
                        "errors": self.daytona_result.errors,
                    }
                    if self.daytona_result
                    else None
                ),
            },
        }

    def print_summary(self):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("PHASE 2 PROFILE PARITY HARNESS - SUMMARY")
        print("=" * 70)
        print(f"Timestamp: {self.timestamp}")
        print(f"Overall Success: {'✓ PASS' if self.overall_success else '✗ FAIL'}")
        print(f"Parity Check: {'✓ PASS' if self.parity_check_passed else '✗ FAIL'}")

        if self.local_result:
            print("\n--- Local Compose Profile ---")
            print(f"  Status: {'✓ PASS' if self.local_result.success else '✗ FAIL'}")
            print(
                f"  Tests: {self.local_result.tests_passed} passed, {self.local_result.tests_failed} failed"
            )
            print(f"  Duration: {self.local_result.duration_seconds:.2f}s")
            if self.local_result.errors:
                print(f"  Errors: {len(self.local_result.errors)}")

        if self.daytona_result:
            print("\n--- Daytona Profile ---")
            print(f"  Status: {'✓ PASS' if self.daytona_result.success else '✗ FAIL'}")
            print(
                f"  Tests: {self.daytona_result.tests_passed} passed, {self.daytona_result.tests_failed} failed"
            )
            print(f"  Duration: {self.daytona_result.duration_seconds:.2f}s")
            if self.daytona_result.errors:
                print(f"  Errors: {len(self.daytona_result.errors)}")

        if not self.parity_check_passed and self.local_result and self.daytona_result:
            print("\n--- Parity Differences ---")
            if self.local_result.success != self.daytona_result.success:
                print("  ✗ Profile success status differs")
            if (
                self.local_result.tests_passed != self.daytona_result.tests_passed
                or self.local_result.tests_failed != self.daytona_result.tests_failed
            ):
                print("  ✗ Test counts differ between profiles")

        print("=" * 70)


def run_tests_for_profile(
    profile: str, verbose: bool = False, test_filter: Optional[str] = None
) -> ProfileResult:
    """Run integration tests under a specific profile.

    Args:
        profile: The sandbox profile to use ('local_compose' or 'daytona')
        verbose: Whether to show test output
        test_filter: Optional pytest -k filter expression

    Returns:
        ProfileResult with test outcomes
    """
    import time

    start_time = time.time()

    # Set environment for this profile
    env = os.environ.copy()
    env["SANDBOX_PROFILE"] = profile

    # Build pytest command
    cmd = [
        "python",
        "-m",
        "pytest",
        "src/tests/integration/test_phase2_run_routing_errors.py",
        "-v" if verbose else "-q",
    ]

    if test_filter:
        cmd.extend(["-k", test_filter])

    # Add fail-fast for CI mode
    cmd.append("--tb=short")

    print(f"\n[HARNESS] Running tests with profile: {profile}")
    print(f"[HARNESS] Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5 minute timeout
        )

        duration = time.time() - start_time

        # Parse test results from output
        output = result.stdout + "\n" + result.stderr

        # Extract test counts from pytest output
        tests_passed = 0
        tests_failed = 0
        errors = []

        # Parse "X passed" and "Y failed" from output
        for line in output.split("\n"):
            if " passed" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "passed":
                            tests_passed = int(parts[i - 1])
                            break
                except (ValueError, IndexError):
                    pass
            if " failed" in line:
                try:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "failed":
                            tests_failed = int(parts[i - 1])
                            break
                except (ValueError, IndexError):
                    pass
            if "ERROR" in line or "error" in line.lower():
                errors.append(line.strip())

        success = result.returncode == 0 and tests_failed == 0

        return ProfileResult(
            profile=profile,
            success=success,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            errors=errors[:10],  # Limit error details
            output=output if verbose else "",
            duration_seconds=duration,
        )

    except subprocess.TimeoutExpired:
        return ProfileResult(
            profile=profile,
            success=False,
            tests_passed=0,
            tests_failed=0,
            errors=["Test execution timed out after 300 seconds"],
            output="",
            duration_seconds=300.0,
        )
    except Exception as e:
        return ProfileResult(
            profile=profile,
            success=False,
            tests_passed=0,
            tests_failed=0,
            errors=[f"Test execution failed: {str(e)}"],
            output="",
            duration_seconds=0.0,
        )


def check_parity(local_result: ProfileResult, daytona_result: ProfileResult) -> bool:
    """Check if results are equivalent across profiles.

    Args:
        local_result: Results from local_compose profile
        daytona_result: Results from daytona profile

    Returns:
        True if profiles show parity (equivalent outcomes)
    """
    # Both should succeed (or both fail for same reasons)
    if local_result.success != daytona_result.success:
        return False

    # Test counts should match
    if local_result.tests_passed != daytona_result.tests_passed:
        return False

    if local_result.tests_failed != daytona_result.tests_failed:
        return False

    return True


def run_ci_mode(args) -> int:
    """Run in CI mode: execute both profiles and check parity.

    CI mode requires:
    1. local_compose profile tests must pass
    2. daytona profile tests must pass (credentials required)
    3. Parity check must pass (both profiles have equivalent outcomes)

    Unlike local mode, CI mode will FAIL if Daytona credentials are missing.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 70)
    print("PHASE 2 PROFILE PARITY HARNESS - CI MODE")
    print("=" * 70)
    print("[HARNESS] CI mode requires both local_compose and daytona profiles")
    print(
        "[HARNESS] Truth 11: Valid pack runs with equivalent semantics across profiles"
    )
    print()

    report = ParityReport()

    # Run local_compose profile
    report.local_result = run_tests_for_profile(
        "local_compose",
        verbose=args.verbose,
        test_filter=args.test_filter,
    )

    # Check if Daytona credentials are available (REQUIRED in CI mode)
    daytona_api_key = os.environ.get("DAYTONA_API_KEY") or os.environ.get(
        "DAYTONA_API_TOKEN"
    )

    if not daytona_api_key:
        print("\n[HARNESS] ERROR: DAYTONA_API_KEY not set")
        print(
            "[HARNESS] CI mode requires Daytona credentials for profile parity verification"
        )
        print("[HARNESS] Set DAYTONA_API_KEY environment variable")
        report.overall_success = False
        report.parity_check_passed = False
        report.print_summary()
        return 1

    # Run daytona profile (required in CI mode)
    report.daytona_result = run_tests_for_profile(
        "daytona",
        verbose=args.verbose,
        test_filter=args.test_filter,
    )

    # Check parity between profiles
    report.parity_check_passed = check_parity(
        report.local_result, report.daytona_result
    )

    # Overall success: BOTH profiles must pass AND parity must pass
    report.overall_success = (
        report.local_result.success
        and report.daytona_result.success
        and report.parity_check_passed
    )

    # Print summary
    report.print_summary()

    # Export results if requested
    if args.output:
        import json

        # Ensure output directory exists
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(args.output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\n[HARNESS] Results exported to: {args.output}")

    return 0 if report.overall_success else 1


def run_local_mode(args) -> int:
    """Run in local mode: single profile execution.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    profile = args.profile or os.environ.get("SANDBOX_PROFILE", "local_compose")

    print("=" * 70)
    print(f"PHASE 2 PROFILE PARITY HARNESS - LOCAL MODE ({profile})")
    print("=" * 70)

    result = run_tests_for_profile(
        profile,
        verbose=args.verbose,
        test_filter=args.test_filter,
    )

    print(f"\nProfile: {result.profile}")
    print(f"Status: {'✓ PASS' if result.success else '✗ FAIL'}")
    print(f"Tests: {result.tests_passed} passed, {result.tests_failed} failed")
    print(f"Duration: {result.duration_seconds:.2f}s")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:5]:
            print(f"  - {error}")

    return 0 if result.success else 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phase 2 Profile Parity Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in CI mode (both profiles)
  uv run python src/scripts/phase2_profile_parity_harness.py --mode ci

  # Run local profile only with verbose output
  uv run python src/scripts/phase2_profile_parity_harness.py --mode local --verbose

  # Run specific tests with Daytona profile
  uv run python src/scripts/phase2_profile_parity_harness.py --mode local --profile daytona -k "fail_fast"

  # Export results to JSON
  uv run python src/scripts/phase2_profile_parity_harness.py --mode ci --output results.json
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["ci", "local"],
        default="local",
        help="Execution mode: ci (both profiles) or local (single profile)",
    )

    parser.add_argument(
        "--profile",
        choices=["local_compose", "daytona"],
        default=None,
        help="Sandbox profile to use (local mode only, defaults to SANDBOX_PROFILE env var)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose test output",
    )

    parser.add_argument(
        "-k",
        "--test-filter",
        metavar="EXPRESSION",
        help="Pytest -k filter expression (e.g., 'fail_fast')",
    )

    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Export results to JSON file",
    )

    args = parser.parse_args()

    if args.mode == "ci":
        return run_ci_mode(args)
    else:
        return run_local_mode(args)


if __name__ == "__main__":
    sys.exit(main())
