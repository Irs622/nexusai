"""Architecture Enforcement Test Suite — Rules A002 & A003 (Provider Isolation).

Rule A002: runtime MUST NOT import concrete provider adapters.
Rule A003: brain MUST depend only on provider abstractions, NEVER concrete adapters.
"""

from pathlib import Path

from nexusai.architecture.dependency_rules import DependencyRulesEngine

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_rule_a002_runtime_must_not_import_concrete_providers():
    """Verify Rule A002: nexusai.runtime MUST NOT import concrete provider adapters."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a002()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A002 violated! Found {len(violations)} concrete provider import(s) "
            f"in 'nexusai.runtime':\n\n{reports}"
        )
        raise AssertionError(msg)


def test_rule_a003_brain_must_depend_only_on_provider_abstractions():
    """Verify Rule A003: nexusai.brain MUST depend only on provider abstractions, NEVER concrete adapters."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a003()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A003 violated! Found {len(violations)} concrete provider import(s) "
            f"in 'nexusai.brain':\n\n{reports}"
        )
        raise AssertionError(msg)
