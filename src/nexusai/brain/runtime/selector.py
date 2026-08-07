"""
ProviderSelector capability negotiation engine building execution plans.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from nexusai.brain.runtime.capabilities import RequiredCapabilities
from nexusai.brain.runtime.plan import ExecutionPlan, ExecutionStep
from nexusai.logging.logger import logger


class ProviderSelector:
    """Selects target model routes and negotiates capabilities to build ExecutionPlans."""

    def __init__(self, provider_registry: Any | None = None) -> None:
        """Initialize ProviderSelector with optional provider registry reference.

        Args:
            provider_registry: Optional reference to ProviderRegistry (nexusai.providers).
        """
        self._provider_registry = provider_registry

    def select_plan(
        self,
        capabilities: RequiredCapabilities,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
    ) -> ExecutionPlan:
        """Negotiate capabilities and construct an ExecutionPlan with primary and fallback routes.

        Args:
            capabilities: Required model capabilities requested by the client or agent.
            preferred_provider: Optional explicit provider override.
            preferred_model: Optional explicit model override.

        Returns:
            An immutable ExecutionPlan containing primary and fallback ExecutionSteps.
        """
        logger.bind(
            requested_caps=list(capabilities.capabilities),
            preferred_provider=preferred_provider,
            preferred_model=preferred_model,
        ).debug("Negotiating capabilities")

        # 1. Direct explicit preference resolution
        primary_provider = preferred_provider or "openrouter"
        primary_model = preferred_model or "anthropic/claude-3.5-sonnet"

        # 2. Check local model preference in constraints
        if capabilities.constraints.prefer_local:
            primary_provider = "ollama"
            primary_model = preferred_model or "llama3:latest"

        # 3. Construct primary execution step
        primary_step = ExecutionStep(
            step_id=uuid4().hex[:8],
            step_type="provider_invocation",
            provider_id=primary_provider,
            model_id=primary_model,
            parameters={
                "required_capabilities": list(capabilities.capabilities),
                "min_context_window": capabilities.constraints.min_context_window,
            },
        )

        # 4. Construct resilient fallback steps
        fallback_steps: list[ExecutionStep] = []
        if primary_provider != "openrouter":
            fallback_steps.append(
                ExecutionStep(
                    step_id=uuid4().hex[:8],
                    step_type="fallback_invocation",
                    provider_id="openrouter",
                    model_id="anthropic/claude-3.5-sonnet",
                    parameters={"reason": "fallback_secondary"},
                )
            )

        if primary_provider != "gemini":
            fallback_steps.append(
                ExecutionStep(
                    step_id=uuid4().hex[:8],
                    step_type="fallback_invocation",
                    provider_id="gemini",
                    model_id="gemini-1.5-pro",
                    parameters={"reason": "fallback_tertiary"},
                )
            )

        plan = ExecutionPlan(
            steps=(primary_step,),
            fallback_chain=tuple(fallback_steps),
        )

        logger.info(
            f"ExecutionPlan constructed: primary='{primary_provider}/{primary_model}', fallbacks={len(fallback_steps)}"
        )
        return plan
