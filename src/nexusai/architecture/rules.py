"""Data-Driven Architecture Rule Definitions for NexusAI.

Declarative rules engine matching package dependency boundary directives defined in
the NexusAI Project Constitution (docs/concepts/architecture_manifesto.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set


@dataclass(frozen=True)
class ArchitectureRule:
    rule_id: str
    target_package: str
    description: str
    forbidden_package_prefixes: Set[str] = field(default_factory=set)
    forbidden_symbols: Set[str] = field(default_factory=set)


# Declarative Data-Driven Architecture Rules Registry
ARCHITECTURE_RULES: List[ArchitectureRule] = [
    ArchitectureRule(
        rule_id="A001",
        target_package="providers",
        description="providers package MUST NOT import runtime, brain, memory, workflow, automation",
        forbidden_package_prefixes={
            "nexusai.runtime",
            "nexusai.brain",
            "nexusai.memory",
            "nexusai.workflow",
            "nexusai.automation",
        },
    ),
    ArchitectureRule(
        rule_id="A002",
        target_package="runtime",
        description="runtime MUST NOT import concrete provider adapters",
        forbidden_package_prefixes={
            "nexusai.providers.openrouter",
            "nexusai.providers.gemini",
            "nexusai.providers.anthropic",
            "nexusai.providers.ollama",
            "nexusai.providers.openai",
        },
        forbidden_symbols={
            "OpenAIProvider",
            "OpenRouterProvider",
            "GeminiProvider",
            "AnthropicProvider",
            "OllamaProvider",
        },
    ),
    ArchitectureRule(
        rule_id="A003",
        target_package="brain",
        description="brain MUST depend only on provider abstractions, NEVER concrete adapters",
        forbidden_package_prefixes={
            "nexusai.providers.openrouter",
            "nexusai.providers.gemini",
            "nexusai.providers.anthropic",
            "nexusai.providers.ollama",
            "nexusai.providers.openai",
        },
        forbidden_symbols={
            "OpenAIProvider",
            "OpenRouterProvider",
            "GeminiProvider",
            "AnthropicProvider",
            "OllamaProvider",
        },
    ),
    ArchitectureRule(
        rule_id="A004",
        target_package="memory",
        description="memory MUST remain provider-independent",
        forbidden_package_prefixes={"nexusai.providers"},
    ),
    ArchitectureRule(
        rule_id="A005",
        target_package="workflow",
        description="workflow MUST remain provider-independent",
        forbidden_package_prefixes={
            "nexusai.providers.openrouter",
            "nexusai.providers.gemini",
            "nexusai.providers.anthropic",
            "nexusai.providers.ollama",
            "nexusai.providers.openai",
        },
        forbidden_symbols={
            "OpenAIProvider",
            "OpenRouterProvider",
            "GeminiProvider",
            "AnthropicProvider",
            "OllamaProvider",
        },
    ),
    ArchitectureRule(
        rule_id="A006",
        target_package="security",
        description="security layer MUST NOT import concrete provider implementations",
        forbidden_package_prefixes={
            "nexusai.providers.openrouter",
            "nexusai.providers.gemini",
            "nexusai.providers.anthropic",
            "nexusai.providers.ollama",
            "nexusai.providers.openai",
        },
        forbidden_symbols={
            "OpenAIProvider",
            "OpenRouterProvider",
            "GeminiProvider",
            "AnthropicProvider",
            "OllamaProvider",
        },
    ),
    ArchitectureRule(
        rule_id="A007",
        target_package="brain",
        description="Core packages MUST NOT instantiate concrete providers directly (DI Enforcement)",
        forbidden_symbols={
            "OpenAIProvider",
            "OpenRouterProvider",
            "GeminiProvider",
            "AnthropicProvider",
            "OllamaProvider",
        },
    ),
    ArchitectureRule(
        rule_id="A008",
        target_package="brain",
        description="Core packages MUST resolve providers only through ProviderRegistry",
        forbidden_symbols=set(),
    ),
]
