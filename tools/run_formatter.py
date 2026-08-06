"""
Modular Code Formatter Runner Script for NexusAI.
Runs Black and isort check across src, tests, benchmarks, and tools.
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


def run_formatter(fix: bool = False) -> int:
    """Execute formatting check or auto-formatting."""
    target_dirs = ["src", "tests", "benchmarks", "tools"]
    existing_dirs = [d for d in target_dirs if (PROJECT_ROOT / d).exists()]

    print("=== [Quality Gate] Running Code Formatter Check (Black & isort) ===")

    isort_ok = True
    black_ok = True

    if _is_module_available("isort"):
        isort_cmd = [sys.executable, "-m", "isort"]
        if not fix:
            isort_cmd.append("--check-only")
        isort_cmd.extend(existing_dirs)
        print(f"Running isort: {' '.join(isort_cmd)}")
        res_isort = subprocess.run(isort_cmd, cwd=PROJECT_ROOT)
        isort_ok = res_isort.returncode == 0
    else:
        print("⚠️ Module 'isort' not installed in environment, skipping isort check.")

    if _is_module_available("black"):
        black_cmd = [sys.executable, "-m", "black"]
        if not fix:
            black_cmd.append("--check")
        black_cmd.extend(existing_dirs)
        print(f"Running Black: {' '.join(black_cmd)}")
        res_black = subprocess.run(black_cmd, cwd=PROJECT_ROOT)
        black_ok = res_black.returncode == 0
    else:
        print("⚠️ Module 'black' not installed in environment, skipping black check.")

    if not isort_ok or not black_ok:
        print("❌ Code Formatter Check Failed!")
        return 1

    print("✅ Code Formatter Check Passed Successfully!")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Formatter Runner")
    parser.add_argument("--fix", action="store_true", help="Auto-fix formatting issues")
    args = parser.parse_args()

    sys.exit(run_formatter(fix=args.fix))
