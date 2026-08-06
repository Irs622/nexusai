"""
Modular Code Formatter Runner Script for NexusAI.
Runs Black and isort check across src, tests, benchmarks, and tools.
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def run_formatter(fix: bool = False) -> int:
    """Execute formatting check or auto-formatting."""
    target_dirs = ["src", "tests", "benchmarks", "tools"]
    existing_dirs = [d for d in target_dirs if (PROJECT_ROOT / d).exists()]
    
    black_cmd = [sys.executable, "-m", "black"]
    isort_cmd = [sys.executable, "-m", "isort"]
    
    if not fix:
        black_cmd.append("--check")
        isort_cmd.append("--check-only")
    
    black_cmd.extend(existing_dirs)
    isort_cmd.extend(existing_dirs)
    
    print("=== [Quality Gate] Running Code Formatter Check (Black & isort) ===")
    
    print(f"Running isort: {' '.join(isort_cmd)}")
    res_isort = subprocess.run(isort_cmd, cwd=PROJECT_ROOT)
    
    print(f"Running Black: {' '.join(black_cmd)}")
    res_black = subprocess.run(black_cmd, cwd=PROJECT_ROOT)
    
    if res_isort.returncode != 0 or res_black.returncode != 0:
        print("❌ Code Formatter Check Failed!")
        return 1
    
    print("✅ Code Formatter Check Passed Successfully!")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Formatter Runner")
    parser.add_argument("--fix", action="store_true", help="Auto-fix formatting issues")
    args = parser.parse_args()
    
    sys.exit(run_formatter(fix=args.fix))
