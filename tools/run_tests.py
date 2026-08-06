"""
Modular Tiered Test Suite & Package Coverage Runner Script for NexusAI.

Provides explicit execution modes for tiered test matrix:
- Local (default): unit + architecture + snapshot
- CI PR (--ci-pr): + integration + contract
- Nightly (--nightly): all tiers
- Explicit tier flags: --unit, --integration, --contract, --benchmark, --stress, --network, --snapshot, --architecture
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).parent.parent


def run_tests(
    mode: str = "local",
    verbose: bool = False,
    coverage: bool = False,
    fail_fast: bool = False,
) -> int:
    """Execute pytest with specific marker filters based on mode."""
    pytest_cmd = [sys.executable, "-m", "pytest"]

    if verbose:
        pytest_cmd.append("-v")

    if fail_fast:
        pytest_cmd.append("-x")

    # Marker expression selection based on mode
    if mode == "unit":
        pytest_cmd.extend(["-m", "not network and not integration and not contract and not benchmark and not stress and not snapshot"])
    elif mode == "local":
        # Local default: unit, architecture, snapshot
        pytest_cmd.extend(["-m", "not network and not integration and not contract and not benchmark and not stress"])
    elif mode == "ci-pr":
        # CI PR: unit, architecture, snapshot, integration, contract
        pytest_cmd.extend(["-m", "not network and not benchmark and not stress"])
    elif mode == "nightly" or mode == "all":
        # Run everything
        pass
    elif mode == "integration":
        pytest_cmd.extend(["-m", "integration"])
    elif mode == "contract":
        pytest_cmd.extend(["-m", "contract"])
    elif mode == "network":
        pytest_cmd.extend(["-m", "network"])
    elif mode == "snapshot":
        pytest_cmd.extend(["-m", "snapshot"])
    elif mode == "architecture":
        pytest_cmd.append("tests/architecture")
        pytest_cmd.extend(["-m", "architecture or not architecture"])

    pytest_cmd.append("--ignore=tests/acceptance")

    if coverage:
        pytest_cmd.extend([
            "--cov=src/nexusai",
            "--cov-branch",
            "--cov-report=term-missing",
            "--ignore=tests/acceptance",
        ])

    pytest_cmd.append("tests")

    print(f"=== [Quality Gate] Running Test Suite (Mode: {mode}) ===")
    print(f"Running command: {' '.join(pytest_cmd)}")

    res = subprocess.run(pytest_cmd, cwd=PROJECT_ROOT)

    if res.returncode != 0:
        print(f"❌ Test Suite ({mode}) Failed!")
        return res.returncode

    print(f"✅ Test Suite ({mode}) Passed Successfully!")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Tiered Test Runner")
    parser.add_argument(
        "--mode",
        choices=["local", "unit", "ci-pr", "nightly", "all", "integration", "contract", "network", "snapshot", "architecture"],
        default="local",
        help="Test execution mode (default: local)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose pytest output")
    parser.add_argument("-x", "--exitfirst", action="store_true", help="Exit on first failure")
    parser.add_argument("--cov", action="store_true", help="Enable coverage reporting")

    args = parser.parse_args()

    sys.exit(
        run_tests(
            mode=args.mode,
            verbose=args.verbose,
            coverage=args.cov,
            fail_fast=args.exitfirst,
        )
    )
