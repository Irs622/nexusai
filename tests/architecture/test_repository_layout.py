"""Architecture Fitness Test — Repository Layout & Tooling Package Isolation.

Enforces Section 8 of AGENTS.md:
- benchmarks/ must remain a valid repository-level tooling package.
- src/nexusai MUST NOT import benchmarks or root tooling.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_benchmarks_package_marker_exists():
    """Verify benchmarks/ contains an __init__.py package marker."""
    benchmarks_init = PROJECT_ROOT / "benchmarks" / "__init__.py"
    assert benchmarks_init.exists(), "benchmarks/__init__.py MUST exist as a valid package marker!"


def test_src_nexusai_does_not_import_benchmarks():
    """Verify application code under src/nexusai DOES NOT import benchmarks package."""
    src_dir = PROJECT_ROOT / "src" / "nexusai"

    violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        if "import benchmarks" in code or "from benchmarks" in code:
            violations.append(str(py_file.relative_to(PROJECT_ROOT)))

    assert (
        not violations
    ), f"src/nexusai application code illegally imports benchmarks in: {violations}"


if __name__ == "__main__":
    test_benchmarks_package_marker_exists()
    test_src_nexusai_does_not_import_benchmarks()
    print("ALL REPOSITORY LAYOUT FITNESS TESTS PASSED SUCCESSFULLY!")
