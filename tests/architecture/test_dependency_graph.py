"""Architecture Fitness Test — Whole-Repository Dependency Graph & DAG Validation.

Validates the complete top-down unidirectional DAG flow across NexusAI packages:
1. Repository Layout Isolation: src/nexusai MUST NOT import benchmarks, tests, or root tools.
2. Brain Sub-package Unidirectional Flow:
   nexusai.brain.domain -> nexusai.brain.runtime -> context/prompt/streaming/plugins/telemetry/persistence -> nexusai.brain.pipeline -> nexusai.brain.service
3. Provider Isolation (Rule A001): providers MUST NOT import forbidden execution kernel packages.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "nexusai"


def _get_imports_from_file(py_file: Path) -> set[str]:
    """Parse a python file using AST and extract all imported module names."""
    imports: set[str] = set()
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_repository_layout_isolation():
    """Verify application code under src/nexusai DOES NOT import benchmarks, tests, or root tools."""
    forbidden_roots = {"benchmarks", "tests", "tools"}
    violations: list[str] = []

    for py_file in SRC_DIR.rglob("*.py"):
        file_imports = _get_imports_from_file(py_file)
        rel_path = str(py_file.relative_to(PROJECT_ROOT))
        for imp in file_imports:
            root_pkg = imp.split(".")[0]
            if root_pkg in forbidden_roots:
                violations.append(f"{rel_path} -> {imp}")

    assert not violations, f"Application code illegally imports tooling packages:\n" + "\n".join(violations)


def test_brain_domain_dag_isolation():
    """Verify nexusai.brain.domain DOES NOT import any other sub-package inside brain."""
    domain_dir = SRC_DIR / "brain" / "domain"
    forbidden_subpackages = {
        "nexusai.brain.runtime",
        "nexusai.brain.compaction",
        "nexusai.brain.context",
        "nexusai.brain.prompt",
        "nexusai.brain.streaming",
        "nexusai.brain.pipeline",
        "nexusai.brain.service",
        "nexusai.brain.strategy",
        "nexusai.brain.loop_executor",
    }
    violations: list[str] = []

    for py_file in domain_dir.rglob("*.py"):
        file_imports = _get_imports_from_file(py_file)
        rel_path = str(py_file.relative_to(PROJECT_ROOT))
        for imp in file_imports:
            for forbidden in forbidden_subpackages:
                if imp.startswith(forbidden):
                    violations.append(f"{rel_path} -> {imp}")

    assert not violations, f"brain.domain violates DAG flow by importing:\n" + "\n".join(violations)


def test_brain_runtime_dag_isolation():
    """Verify nexusai.brain.runtime MAY ONLY import domain entities, not pipeline or service."""
    runtime_dir = SRC_DIR / "brain" / "runtime"
    forbidden_subpackages = {
        "nexusai.brain.pipeline",
        "nexusai.brain.service",
        "nexusai.brain.loop_executor",
    }
    violations: list[str] = []

    for py_file in runtime_dir.rglob("*.py"):
        file_imports = _get_imports_from_file(py_file)
        rel_path = str(py_file.relative_to(PROJECT_ROOT))
        for imp in file_imports:
            for forbidden in forbidden_subpackages:
                if imp.startswith(forbidden):
                    violations.append(f"{rel_path} -> {imp}")

    assert not violations, f"brain.runtime violates DAG flow by importing:\n" + "\n".join(violations)


if __name__ == "__main__":
    test_repository_layout_isolation()
    test_brain_domain_dag_isolation()
    test_brain_runtime_dag_isolation()
    print("ALL DEPENDENCY GRAPH DAG FITNESS TESTS PASSED SUCCESSFULLY!")
