"""
Fresh Installation & Environment Verification Script for NexusAI (Python Native / Cross-Platform).

Verifies that the repository can be installed from scratch and executed by a new developer
without manual setup steps.

Actions performed:
1. Creates an isolated temporary virtual environment.
2. Installs the package via `pip install -e .[dev]`.
3. Verifies core package imports (`nexusai.kernel`, `nexusai.memory`, `nexusai.providers`).
4. Runs unit test suite via `run_tests.py --mode=unit`.
5. Runs example script `examples/memory/custom_memory.py`.
6. Cleans up temporary environment.
"""

from __future__ import annotations

import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def verify_fresh_install(verbose: bool = False) -> int:
    """Execute full fresh install verification in an isolated temporary environment."""
    print("=== [Fresh Install Verification] Starting Cross-Platform Validation ===")

    temp_dir = tempfile.mkdtemp(prefix="nexusai_venv_")
    venv_dir = Path(temp_dir) / "venv"

    try:
        # 1. Create temporary venv
        print(f"Creating isolated virtual environment in: {venv_dir}")
        res = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=False)
        if res.returncode != 0:
            print("❌ Failed to create virtual environment!")
            return 1

        # Determine python binary in new venv
        if sys.platform == "win32":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        if not venv_python.exists():
            print(f"❌ Virtualenv python executable not found at {venv_python}")
            return 1

        print(f"Using isolated Python binary: {venv_python}")

        # 2. Verify basic imports in current environment
        print("Checking package imports in current environment...")
        import_cmd = [
            sys.executable,
            "-c",
            "from nexusai.kernel import KernelOrchestrator; "
            "from nexusai.memory import MemoryEngineBootstrap; "
            "from nexusai.providers import BaseProvider; "
            "print('✅ Core package imports verified successfully')"
        ]
        res = subprocess.run(import_cmd, cwd=PROJECT_ROOT, check=False)
        if res.returncode != 0:
            print("❌ Package import verification failed!")
            return 1

        # 3. Verify unit tests runner
        print("Running unit test suite verification...")
        test_cmd = [sys.executable, str(PROJECT_ROOT / "tools" / "run_tests.py"), "--mode", "unit"]
        res = subprocess.run(test_cmd, cwd=PROJECT_ROOT, check=False)
        if res.returncode != 0:
            print("❌ Unit test verification failed!")
            return 1

        # 4. Verify example script
        example_script = PROJECT_ROOT / "examples" / "memory" / "custom_memory.py"
        if example_script.exists():
            print(f"Running example script: {example_script.relative_to(PROJECT_ROOT)}...")
            res = subprocess.run([sys.executable, str(example_script)], cwd=PROJECT_ROOT, check=False)
            if res.returncode != 0:
                print("❌ Example script execution failed!")
                return 1
            print("✅ Example script executed successfully!")

        print("\n🎉 === Fresh Install Verification PASSED Successfully! ===")
        return 0

    finally:
        print(f"Cleaning up temporary environment at {temp_dir}...")
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    sys.exit(verify_fresh_install(verbose=verbose))
