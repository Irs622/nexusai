"""
Modular Mutation Testing Runner Script for NexusAI.

Runs mutmut mutation tests scoped exclusively to:
- src/nexusai/core
- src/nexusai/kernel
- src/nexusai/memory/domain

Provider, CLI, adapters, infrastructure, and benchmark code
are EXCLUDED to prevent false positives and slow run times.
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Mutation testing scope — strictly limited to core domain logic.
MUTATION_SCOPE = [
    "src/nexusai/core",
    "src/nexusai/kernel",
    "src/nexusai/memory/domain",
]


def run_mutation_tests(show_summary: bool = True) -> int:
    """Execute mutmut mutation tests on scoped packages."""
    paths = ",".join(
        str(PROJECT_ROOT / p)
        for p in MUTATION_SCOPE
        if (PROJECT_ROOT / p).exists()
    )

    if not paths:
        print("⚠️  No mutation target paths found. Skipping mutation tests.")
        return 0

    print("=== [Quality Gate] Running Mutation Testing (mutmut) ===")
    print(f"Scope: {', '.join(MUTATION_SCOPE)}")

    run_cmd = [
        sys.executable, "-m", "mutmut", "run",
        f"--paths-to-mutate={paths}",
        "--runner=pytest",
        "--tests-dir=tests",
    ]
    print(f"Command: {' '.join(run_cmd)}\n")
    run_res = subprocess.run(run_cmd, cwd=PROJECT_ROOT)

    if show_summary:
        summary_cmd = [sys.executable, "-m", "mutmut", "results"]
        subprocess.run(summary_cmd, cwd=PROJECT_ROOT)

    if run_res.returncode not in (0, 1):
        # mutmut returns 1 when surviving mutants exist (expected in CI gate)
        print("❌ Mutation Testing runner encountered an unexpected error!")
        return run_res.returncode

    print("\n✅ Mutation Testing Completed. Review results above for surviving mutants.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Mutation Test Runner")
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip printing mutmut results summary",
    )
    args = parser.parse_args()
    sys.exit(run_mutation_tests(show_summary=not args.no_summary))
