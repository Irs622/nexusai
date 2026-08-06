"""
Unified Master Quality Gate Runner for Local Developers (NexusAI).

Executes Quality Gate Checks in Two Stages:
- Stage 1 (Parallel): Formatter, Linter, Static Type Checker
- Stage 2 (Sequential): Architecture Compliance, Test Suite & Coverage, Benchmark Regressions
"""

import sys
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    start_time = time.perf_counter()
    print("======================================================================")
    print("           NexusAI Master Quality Gate Verification Pipeline           ")
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
    # Stage 2: Sequential Verification (Architecture, Tests, Benchmarks)
    # ------------------------------------------------------------------
    print("🔹 STAGE 2: Running Sequential System & Compliance Verification...")
    stage2_tasks = [
        ("Architecture Compliance", "tools/run_architecture_tests.py"),
        ("Test Suite & Coverage", "tools/run_tests.py"),
        ("Benchmark Quality Gate", "benchmarks/check_regressions.py"),
    ]
    
    for name, script in stage2_tasks:
        t0 = time.perf_counter()
        cmd = [sys.executable, str(PROJECT_ROOT / script)]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT)
        t1 = time.perf_counter()
        
        if res.returncode != 0:
            print(f"\n❌ {name} Failed! Aborting Quality Gate.")
            return 1
        print(f"  ✅ {name:<25} [PASSED] ({(t1 - t0):.2f}s)")
        
    total_elapsed = time.perf_counter() - start_time
    print("\n======================================================================")
    print(f"🎉 ALL QUALITY GATES PASSED SUCCESSFULLY! Total time: {total_elapsed:.2f}s")
    print("======================================================================\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
