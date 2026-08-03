"""Automated Conformance Report Generator for Provider SDK Contract Verification."""

from dataclasses import dataclass
import pytest

from nexusai.providers.base import BaseProvider
from tests.contracts.test_provider_contract import (
    verify_provider_api_contract,
    verify_provider_behavior_contract,
)


@dataclass
class ConformanceReport:
    """Report detailing contract test results and compatibility percentage for a provider."""

    provider_id: str
    api_contract_pass: bool
    behavior_contract_pass: bool
    compatibility_percentage: float

    def summary(self) -> str:
        """Generate formatted summary string."""
        return (
            f"=== Conformance Report: {self.provider_id} ===\n"
            f"API Surface Contract: {'✓ PASS' if self.api_contract_pass else '❌ FAIL'}\n"
            f"Runtime Behavior Contract: {'✓ PASS' if self.behavior_contract_pass else '❌ FAIL'}\n"
            f"Overall Compatibility Score: {self.compatibility_percentage:.1f}%\n"
        )


async def generate_conformance_report(provider: BaseProvider) -> ConformanceReport:
    """Generate a ConformanceReport for a target BaseProvider instance."""
    api_pass = False
    behavior_pass = False

    try:
        await verify_provider_api_contract(provider)
        api_pass = True
    except Exception:
        api_pass = False

    try:
        await verify_provider_behavior_contract(provider)
        behavior_pass = True
    except Exception:
        behavior_pass = False

    score = 0.0
    if api_pass and behavior_pass:
        score = 100.0
    elif api_pass or behavior_pass:
        score = 50.0

    return ConformanceReport(
        provider_id=provider.id,
        api_contract_pass=api_pass,
        behavior_contract_pass=behavior_pass,
        compatibility_percentage=score,
    )
