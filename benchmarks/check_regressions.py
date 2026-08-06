"""
Benchmark Quality Gate Regression Checker for NexusAI.

This script delegates to the pluggable benchmark framework:
  benchmarks/collectors/ → benchmarks/comparators/ → benchmarks/reporters/

Intended for direct invocation from CI pipelines.
For local developer use, prefer: python tools/run_benchmarks.py
"""

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.run_benchmarks import run_benchmarks

if __name__ == "__main__":
    # CI quick mode: fewer iterations; still saves snapshot for trend tracking.
    sys.exit(run_benchmarks(quick=True, save=True))
