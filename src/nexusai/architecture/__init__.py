"""Architecture Enforcement package for NexusAI."""

from nexusai.architecture.dependency_rules import (
    ArchitectureRule,
    DependencyViolation,
    DependencyRulesEngine,
    audit_repository_dependencies,
)

__all__ = [
    "ArchitectureRule",
    "DependencyViolation",
    "DependencyRulesEngine",
    "audit_repository_dependencies",
]
