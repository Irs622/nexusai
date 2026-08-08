"""
Security Audit Runner for NexusAI.

Invokes pip-audit to scan installed dependencies for known CVE vulnerabilities.
Fails with non-zero exit code if any HIGH or CRITICAL severity vulnerabilities
are found in the dependency tree.
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_security_audit() -> int:
    """Run pip-audit CVE vulnerability scan.

    Returns:
        0 if no vulnerabilities found, 1 if vulnerabilities detected.
    """
    print("=== [Quality Gate] Running Security Vulnerability Audit (pip-audit) ===\n")

    cmd = [
        sys.executable, "-m", "pip_audit",
        "--requirement", str(PROJECT_ROOT / "requirements.txt"),
        "--format", "columns",
        "--progress-spinner", "off",
    ]

    # Fallback: scan the current environment if pyproject.toml reading fails
    fallback_cmd = [
        sys.executable, "-m", "pip_audit",
        "--format", "columns",
        "--progress-spinner", "off",
    ]

    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode == 2:
        # pip-audit couldn't parse the toml requirement, fall back to env scan
        print("Falling back to environment-wide scan...")
        res = subprocess.run(fallback_cmd, cwd=PROJECT_ROOT)

    if res.returncode == 0:
        print("\n✅ Security Audit Passed — No known vulnerabilities detected!")
        return 0

    print("\n❌ Security Audit FAILED — Vulnerabilities detected. Review output above.")
    return 1


if __name__ == "__main__":
    sys.exit(run_security_audit())
