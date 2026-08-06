"""
Unified Master Quality Gate Runner for Local Developers and Release Candidates (NexusAI).

Executes Quality Gate Checks in Two Stages:
- Stage 1 (Parallel): Formatter, Linter, Static Type Checker
- Stage 2 (Sequential): Architecture Compliance, Test Suite, API Compatibility Snapshots, Benchmarks, Security Audit, and Fresh Install Validation

Usage:
  python tools/run_quality_gate.py            # Standard local gate
  python tools/run_quality_gate.py --release  # Full Release Candidate validation
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).parent.parent


def _run_stage1_task(name: str, script_name: str) -> tuple[str, int, float]:
    """Execute a single Stage 1 task script."""
    t0 = time.perf_counter()
    cmd = [sys.executable, str(PROJECT_ROOT / "tools" / script_name)]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    t1 = time.perf_counter()

    output = res.stdout.strip()
    if res.stderr:
        output += "\n" + res.stderr.strip()

    if res.returncode != 0:
        print(f"\n--- {name} Output --- \n{output}\n-----------------------")

    return name, res.returncode, (t1 - t0)


def main() -> int:
    parser = argparse.ArgumentParser(description="NexusAI Master Quality Gate")
    parser.add_argument("--release", action="store_true", help="Execute full Release Candidate validation pipeline")
    args = parser.parse_args()

    start_time = time.perf_counter()
    gate_title = "Release Candidate Quality Gate" if args.release else "Developer Quality Gate"
    print("======================================================================")
    print(f"           NexusAI Master {gate_title} Verification Pipeline           ")
    print("======================================================================\n")

    # ------------------------------------------------------------------
    # Stage 1: Parallel Execution (Formatter, Linter, Type Checker)
    # ------------------------------------------------------------------
    print("🔹 STAGE 1: Running Static Analysis Tasks in Parallel...")
    stage1_tasks = [
        ("Formatter Check", "run_formatter.py"),
        ("Linter Check", "run_linter.py"),
        ("Type Checker", "run_typecheck.py"),
    ]

    stage1_failed = False
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_stage1_task, name, script): name
            for name, script in stage1_tasks
        }
        for future in as_completed(futures):
            name, code, elapsed = future.result()
            if code == 0:
                print(f"  ✅ {name:<20} [PASSED] ({elapsed:.2f}s)")
            else:
                print(f"  ❌ {name:<20} [FAILED] ({elapsed:.2f}s)")
                stage1_failed = True

    if stage1_failed:
        print("\n❌ Stage 1 Verification Failed! Aborting Stage 2.")
        return 1

    print("\n✅ Stage 1 Passed Successfully!\n")

    # ------------------------------------------------------------------
    # Stage 2: Sequential Verification
    # ------------------------------------------------------------------
    print("🔹 STAGE 2: Running Sequential System & Compliance Verification...")
    stage2_tasks = [
        ("Architecture Compliance", [sys.executable, str(PROJECT_ROOT / "tools" / "run_architecture_tests.py")]),
        ("API Compatibility Snapshots", [sys.executable, "-m", "pytest", "tests/api_compatibility/"]),
        ("Test Suite Verification", [sys.executable, str(PROJECT_ROOT / "tools" / "run_tests.py"), "--mode=local"]),
        ("Benchmark Quality Gate", [sys.executable, str(PROJECT_ROOT / "benchmarks" / "check_regressions.py")]),
    ]

    if args.release:
        stage2_tasks.extend([
            ("Security Audit", [sys.executable, str(PROJECT_ROOT / "tools" / "run_security_audit.py")]),
            ("Fresh Install Validation", [sys.executable, str(PROJECT_ROOT / "tools" / "verify_fresh_install.py")]),
        ])

    for name, cmd in stage2_tasks:
        t0 = time.perf_counter()
        res = subprocess.run(cmd, cwd=PROJECT_ROOT)
        t1 = time.perf_counter()

        if res.returncode != 0:
            print(f"\n❌ {name} Failed! Aborting Quality Gate.")
            return 1
        print(f"  ✅ {name:<30} [PASSED] ({(t1 - t0):.2f}s)")

    total_elapsed = time.perf_counter() - start_time
    print("\n======================================================================")
    print(f"🎉 ALL QUALITY GATES PASSED SUCCESSFULLY! Total time: {total_elapsed:.2f}s")
    print("======================================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
