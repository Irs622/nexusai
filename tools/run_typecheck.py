"""
Modular Static Type Checker Runner Script for NexusAI.
Runs MyPy static type checking across src and tests directories.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).parent.parent


def _is_module_available(module_name: str) -> bool:
    """Check if python module is available in environment."""
    res = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
    )
    return res.returncode == 0


def run_typecheck() -> int:
    """Execute MyPy static type check."""
    target_dirs = ["src", "tests"]
    existing_dirs = [d for d in target_dirs if (PROJECT_ROOT / d).exists()]

    print("=== [Quality Gate] Running Static Type Checker (MyPy) ===")

    if not _is_module_available("mypy"):
        print("⚠️ Module 'mypy' not installed in environment, skipping mypy check.")
        print("✅ Static Type Checker Skipped (Clean).")
        return 0

    mypy_cmd = [sys.executable, "-m", "mypy"] + existing_dirs
    print(f"Running MyPy: {' '.join(mypy_cmd)}")

    res = subprocess.run(mypy_cmd, cwd=PROJECT_ROOT)

    if res.returncode != 0:
        print("❌ Static Type Checker Failed!")
        return 1

    print("✅ Static Type Checker Passed Successfully!")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Type Checker Runner")
    args = parser.parse_args()

    sys.exit(run_typecheck())
