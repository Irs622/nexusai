"""
Modular Static Type Checker Runner Script for NexusAI.
Runs MyPy static type checking across src and tests directories.
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def run_typecheck() -> int:
    """Execute MyPy static type check."""
    target_dirs = ["src", "tests"]
    existing_dirs = [d for d in target_dirs if (PROJECT_ROOT / d).exists()]
    
    mypy_cmd = [sys.executable, "-m", "mypy"] + existing_dirs
    
    print("=== [Quality Gate] Running Static Type Checker (MyPy) ===")
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
