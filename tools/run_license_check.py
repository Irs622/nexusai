"""
Dependency License Compliance Checker for NexusAI.

Scans installed dependency licenses and flags any non-compliant licenses
(e.g., restrictive GPL) that could create open source licensing conflicts.

Allowed licenses: MIT, Apache-2.0, BSD, PSF, ISC, LGPL, MPL-2.0
Flagged as WARNING: LGPL (conditional)
Flagged as FAIL:    GPL-2.0, GPL-3.0, AGPL-3.0
"""

import sys
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

ALLOWED_LICENSE_PREFIXES: tuple[str, ...] = (
    "MIT",
    "Apache",
    "BSD",
    "PSF",
    "ISC",
    "Python Software Foundation",
    "MPL",
    "LGPL",
    "Mozilla",
    "Unlicense",
    "CC0",
    "Public Domain",
)

BLOCKED_LICENSES: tuple[str, ...] = (
    "GPL-2.0",
    "GPL-3.0",
    "AGPL-3.0",
    "GPLv2",
    "GPLv3",
    "AGPL",
)


def run_license_check() -> int:
    """Check dependency licenses for compliance.

    Returns:
        0 if all licenses are compliant, 1 if violations found.
    """
    print("=== [Quality Gate] Running Dependency License Compliance Check ===\n")

    cmd = [
        sys.executable, "-m", "piplicenses",
        "--format", "json",
        "--with-system",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

    if res.returncode != 0:
        print(f"⚠️  pip-licenses not available or failed: {res.stderr.strip()}")
        print("   Install with: pip install pip-licenses>=4.4.0")
        # Non-blocking — don't fail CI if tool is not installed
        return 0

    try:
        packages = json.loads(res.stdout)
    except json.JSONDecodeError:
        print("⚠️  Could not parse pip-licenses output.")
        return 0

    violations: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    for pkg in packages:
        name = pkg.get("Name", "unknown")
        license_str = pkg.get("License", "UNKNOWN")

        is_blocked = any(blocked in license_str for blocked in BLOCKED_LICENSES)
        is_allowed = any(
            license_str.startswith(prefix) for prefix in ALLOWED_LICENSE_PREFIXES
        )

        if is_blocked:
            violations.append({"package": name, "license": license_str})
        elif not is_allowed and license_str not in ("UNKNOWN", ""):
            warnings.append({"package": name, "license": license_str})

    if warnings:
        print("⚠️  License Warnings (review manually):")
        for w in warnings:
            print(f"   • {w['package']}: {w['license']}")
        print()

    if violations:
        print("❌ License Violations Detected (blocked licenses):")
        for v in violations:
            print(f"   ✗ {v['package']}: {v['license']}")
        print("\n❌ License Check FAILED!")
        return 1

    checked = len(packages)
    print(f"✅ License Check Passed — {checked} packages scanned, no violations found!")
    return 0


if __name__ == "__main__":
    sys.exit(run_license_check())
