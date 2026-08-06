"""
Workspace Unit Test Runner Script for NexusAI.
Executes all unit and kernel tests dynamically.
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def main() -> int:
    """Run pytest targeting unit and kernel test directories."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit",
        "tests/kernel",
        "tests/memory/unit",
        "tests/bus",
        "tests/contracts",
        "tests/observability",
        "tests/plugins",
    ]
    print(f"Executing Unit Tests: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return res.returncode

if __name__ == "__main__":
    sys.exit(main())
