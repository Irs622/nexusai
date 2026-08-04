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
    category: str = "BoundaryRules"
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
    ArchitectureRule(
        rule_id="A009",
        target_package="memory.domain",
        description="memory.domain MUST NOT import infrastructure, storage, vector, or embedding",
        forbidden_package_prefixes={
            "nexusai.memory.storage",
            "nexusai.memory.vector",
            "nexusai.memory.embedding",
            "nexusai.memory.pipeline",
            "nexusai.memory.usecases",
        },
    ),
    ArchitectureRule(
        rule_id="A010",
        target_package="memory.repository",
        description="Repositories MUST NOT import other repositories directly",
        forbidden_package_prefixes=set(),
    ),
    ArchitectureRule(
        rule_id="A011",
        target_package="memory.storage",
        description="Storage engines MUST NOT import embedding providers",
        forbidden_package_prefixes={"nexusai.memory.embedding"},
    ),
    ArchitectureRule(
        rule_id="A012",
        target_package="memory.usecases",
        description="UseCases MUST NOT import concrete storage implementations",
        forbidden_package_prefixes={"nexusai.memory.storage.sqlite", "nexusai.memory.storage.file"},
    ),
    ArchitectureRule(
        rule_id="A013",
        target_package="kernel",
        description="kernel MUST NOT import memory module",
        forbidden_package_prefixes={"nexusai.memory"},
    ),
    ArchitectureRule(
        rule_id="A014",
        target_package="memory.pipeline",
        description="RetrievalPipeline MUST remain immutable",
        forbidden_symbols=set(),
    ),
    ArchitectureRule(
        rule_id="A015",
        target_package="memory.embedding",
        description="Embedding Provider MUST NOT import VectorStore",
        forbidden_package_prefixes={"nexusai.memory.vector"},
    ),
    ArchitectureRule(
        rule_id="A016",
        target_package="memory.vector",
        description="VectorStore MUST NOT import Storage",
        forbidden_package_prefixes={"nexusai.memory.storage"},
    ),
    ArchitectureRule(
        rule_id="A017",
        target_package="memory.serializer",
        description="Serializer MUST NOT import Repository",
        forbidden_package_prefixes={"nexusai.memory.repository"},
    ),
    ArchitectureRule(
        rule_id="A018",
        target_package="memory.usecases",
        description="UseCase MUST NOT import concrete Provider directly",
        forbidden_package_prefixes={"nexusai.memory.embedding.local_provider", "nexusai.memory.embedding.remote_provider"},
    ),
    ArchitectureRule(
        rule_id="A019",
        target_package="memory.vector",
        description="Compliance test suites MUST NOT import implementation except target test",
        forbidden_symbols=set(),
    ),
    ArchitectureRule(
        rule_id="A020",
        target_package="memory.pipeline",
        description="PipelineFactory MUST NOT instantiate provider",
        forbidden_package_prefixes={"nexusai.memory.embedding"},
    ),
]
