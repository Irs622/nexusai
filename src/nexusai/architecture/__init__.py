"""Architecture Enforcement package for NexusAI."""

from nexusai.architecture.dependency_rules import (
    DependencyRulesEngine,
    DependencyViolation,
)
from nexusai.architecture.rules import ArchitectureRule

__all__ = [
    "ArchitectureRule",
    "DependencyViolation",
    "DependencyRulesEngine",
]
