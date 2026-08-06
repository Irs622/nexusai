"""
Modular Test Suite & Package Coverage Runner Script for NexusAI.
Executes pytest with branch coverage enforcement and package-specific threshold verification.
"""

import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def run_tests(verbose: bool = False, coverage: bool = True) -> int:
    """Execute pytest test suite with coverage enforcement."""
    pytest_cmd = [sys.executable, "-m", "pytest"]
    
    if verbose:
        pytest_cmd.append("-v")
        
    if coverage:
        pytest_cmd.extend([
            "--cov=src/nexusai",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
            "--ignore=tests/acceptance",
        ])
        
    pytest_cmd.append("tests")
    
    print("=== [Quality Gate] Running Test Suite & Coverage Verification ===")
    print(f"Running pytest: {' '.join(pytest_cmd)}")
    
    res = subprocess.run(pytest_cmd, cwd=PROJECT_ROOT)
    
    if res.returncode != 0:
        print("❌ Test Suite / Coverage Verification Failed!")
        return 1
        
    print("✅ Test Suite & Coverage Verification Passed Successfully!")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusAI Test Runner")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test output")
    parser.add_argument("--no-cov", action="store_true", help="Disable coverage reporting")
    args = parser.parse_args()
    
    sys.exit(run_tests(verbose=args.verbose, coverage=not args.no_cov))
