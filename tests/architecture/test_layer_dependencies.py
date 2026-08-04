"""Architecture Enforcement Test Suite — Rules A004, A005, A006 (Layer Dependencies).

Rule A004: memory MUST remain provider-independent.
Rule A005: workflow MUST remain provider-independent.
Rule A006: security layer MUST NOT import concrete provider implementations.
"""

from pathlib import Path
from nexusai.architecture.dependency_rules import DependencyRulesEngine

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_rule_a004_memory_must_remain_provider_independent():
    """Verify Rule A004: nexusai.memory MUST remain provider-independent."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a004()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A004 violated! Found {len(violations)} provider import(s) "
            f"in 'nexusai.memory':\n\n{reports}"
        )
        raise AssertionError(msg)


def test_rule_a005_workflow_must_remain_provider_independent():
    """Verify Rule A005: nexusai.workflow MUST remain provider-independent."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a005()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A005 violated! Found {len(violations)} concrete provider import(s) "
            f"in 'nexusai.workflow':\n\n{reports}"
        )
        raise AssertionError(msg)


def test_rule_a006_security_must_not_import_concrete_providers():
    """Verify Rule A006: nexusai.security MUST NOT import concrete provider implementations."""
    engine = DependencyRulesEngine(PROJECT_ROOT)
    violations = engine.check_rule_a006()

    if violations:
        reports = "\n\n".join(v.format_report() for v in violations)
        msg = (
            f"Architecture Rule A006 violated! Found {len(violations)} concrete provider import(s) "
            f"in 'nexusai.security':\n\n{reports}"
        )
        raise AssertionError(msg)
