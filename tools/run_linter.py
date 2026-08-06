"""
Modular Linter Runner Script for NexusAI.
Runs Ruff static analysis across src, tests, benchmarks, and tools.
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def run_linter(fix: bool = False) -> int:
    """Execute Ruff linter check or auto-fixing."""
    target_dirs = ["src", "tests", "benchmarks", "tools"]
    existing_dirs = [d for d in target_dirs if (PROJECT_ROOT / d).exists()]
    
    ruff_cmd = [sys.executable, "-m", "ruff", "check"]
    if fix:
        ruff_cmd.append("--fix")
    
    ruff_cmd.extend(existing_dirs)
    
    print("=== [Quality Gate] Running Static Linter Check (Ruff) ===")
    print(f"Running Ruff: {' '.join(ruff_cmd)}")
    
    res = subprocess.run(ruff_cmd, cwd=PROJECT_ROOT)
    
    if res.returncode != 0:
        print("❌ Static Linter Check Failed!")
        return 1
    
    print("✅ Static Linter Check Passed Successfully!")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Linter Runner")
    parser.add_argument("--fix", action="store_true", help="Auto-fix linter warnings/errors")
    args = parser.parse_args()
    
    sys.exit(run_linter(fix=args.fix))
