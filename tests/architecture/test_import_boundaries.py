"""Architecture Enforcement Test Suite — Rule A001 (Import Boundaries).

Rule A001: providers package MUST NOT import runtime, brain, memory, workflow, automation.
"""

from pathlib import Path
from nexusai.architecture.dependency_rules import DependencyRulesEngine

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_rule_a001_providers_must_not_import_forbidden_packages():
    """Verify Rule A001: nexusai.providers MUST NOT import forbidden execution kernel packages."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a001()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A001 violated! Found {len(violations)} forbidden import(s) "
            f"in 'nexusai.providers' importing from forbidden kernel packages "
            f"(runtime, brain, memory, workflow, automation):\n\n{reports}"
        )
        raise AssertionError(msg)
