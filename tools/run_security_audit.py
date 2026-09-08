"""
Security Audit Runner for NexusAI.

Invokes pip-audit to scan installed dependencies for known CVE vulnerabilities.
Fails with non-zero exit code if any HIGH or CRITICAL severity vulnerabilities
are found in the dependency tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Authoritative registry of approved vulnerability exceptions.
# Each entry MUST document: (vulnerability_id, package, rationale).
# ChromaDB 1.5.9 has 4 server-mode CVEs in multi-tenant HTTP routes (/api/v2/tenants/...).
# NexusAI uses ChromaDB exclusively in embedded/in-process storage mode and does NOT
# expose ChromaDB server HTTP endpoints, rendering these attack vectors non-viable.
APPROVED_VULN_EXCEPTIONS: list[tuple[str, str, str]] = [
    (
        "PYSEC-2026-311",
        "chromadb",
        "ChromaDB server API pre-auth code injection (server endpoints not exposed; embedded mode only)",
    ),
    (
        "CVE-2026-45830",
        "chromadb",
        "ChromaDB server authorization validation missing between tenants (NexusAI uses single-tenant embedded storage)",
    ),
    (
        "CVE-2026-45833",
        "chromadb",
        "ChromaDB server model repo code injection via trust_remote_code (remote models disabled in NexusAI)",
    ),
    (
        "CVE-2026-45831",
        "chromadb",
        "ChromaDB SimpleRBAC cross-tenant authorization bypass (embedded storage mode, no server RBAC utilized)",
    ),
]


def run_security_audit() -> int:
    """Run pip-audit CVE vulnerability scan.

    Returns:
        0 if no vulnerabilities found, 1 if vulnerabilities detected.
    """
    print("=== [Quality Gate] Running Security Vulnerability Audit (pip-audit) ===\n")

    ignore_args: list[str] = []
    if APPROVED_VULN_EXCEPTIONS:
        print("Approved Security Vulnerability Exceptions Active:")
        for vuln_id, pkg, reason in APPROVED_VULN_EXCEPTIONS:
            print(f"  - [{vuln_id}] {pkg}: {reason}")
            ignore_args.extend(["--ignore-vuln", vuln_id])
        print()

    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "--requirement",
        str(PROJECT_ROOT / "requirements.txt"),
        "--format",
        "columns",
        "--progress-spinner",
        "off",
    ] + ignore_args

    # Fallback: scan the current environment if requirements.txt reading fails
    fallback_cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "--format",
        "columns",
        "--progress-spinner",
        "off",
    ] + ignore_args

    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode == 2:
        # pip-audit couldn't parse the requirements, fall back to env scan
        print("Falling back to environment-wide scan...")
        res = subprocess.run(fallback_cmd, cwd=PROJECT_ROOT)

    if res.returncode == 0:
        print("\n✅ Security Audit Passed — No unapproved vulnerabilities detected!")
        return 0

    print("\n❌ Security Audit FAILED — Vulnerabilities detected. Review output above.")
    return 1


if __name__ == "__main__":
    sys.exit(run_security_audit())
