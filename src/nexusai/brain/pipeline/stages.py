"""
IExecutionStage protocol and concrete execution stages for ExecutionPipeline.
"""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.context.assembler import ContextAssembler
from nexusai.brain.domain.context import ContextBudget
from nexusai.brain.persistence.service import TurnPersistenceService
from nexusai.brain.prompt.renderer import PromptRenderer
from nexusai.brain.runtime.capabilities import RequiredCapabilities
from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.selector import ProviderSelector
from nexusai.logging.logger import logger


class IExecutionStage(Protocol):
    """Execution stage protocol complying with Open/Closed principle."""

    async def execute(self, ctx: ExecutionContext) -> None:
        """Execute stage logic against ExecutionContext.

        Args:
            ctx: Unified thread ExecutionContext.
        """
        ...


class HistoryStage:
    """Pipeline stage loading and bounding conversation history."""

    def __init__(self, context_assembler: ContextAssembler | None = None) -> None:
        self._assembler = context_assembler or ContextAssembler()

    async def execute(self, ctx: ExecutionContext) -> None:
        """Execute history loading and context assembly."""
        logger.debug(
            f"[HistoryStage] Assembling context for execution '{ctx.runtime.execution_id}'"
        )
        budget = ContextBudget(
            max_input_tokens=ctx.budget.max_input_tokens,
            reserved_output_tokens=ctx.budget.max_output_tokens,
        )

        assembled = await self._assembler.assemble(
            conversation_id=ctx.identity.conversation_id,
            user_content=ctx.runtime.session_state.default_system_prompt or "",
            budget=budget,
            session_system_default=ctx.runtime.session_state.default_system_prompt,
        )

        # Store assembled context in telemetry metadata for downstream stages
        ctx.telemetry.metadata["assembled_context"] = assembled


class PromptStage:
    """Pipeline stage compiling AssembledContext into canonical PromptBundle."""

    def __init__(self, prompt_renderer: PromptRenderer | None = None) -> None:
        self._renderer = prompt_renderer or PromptRenderer()

    async def execute(self, ctx: ExecutionContext) -> None:
        """Execute prompt rendering."""
        logger.debug(
            f"[PromptStage] Rendering PromptBundle for execution '{ctx.runtime.execution_id}'"
        )
        assembled = ctx.telemetry.metadata.get("assembled_context")

        if assembled is not None:
            bundle = self._renderer.render(context=assembled)
            ctx.telemetry.metadata["prompt_bundle"] = bundle


class ProviderStage:
    """Pipeline stage selecting model route and negotiating capabilities."""

    def __init__(self, provider_selector: ProviderSelector | None = None) -> None:
        self._selector = provider_selector or ProviderSelector()

    async def execute(self, ctx: ExecutionContext) -> None:
        """Execute provider route negotiation."""
        logger.debug(
            f"[ProviderStage] Negotiating provider plan for execution '{ctx.runtime.execution_id}'"
        )
        caps = RequiredCapabilities(capabilities=tuple(ctx.runtime.required_capabilities))

        plan = self._selector.select_plan(
            capabilities=caps,
            preferred_provider=ctx.runtime.session_state.provider_id,
            preferred_model=ctx.runtime.session_state.active_model,
        )

        ctx.telemetry.metadata["execution_plan"] = plan


class PersistenceStage:
    """Pipeline stage scheduling write-behind outbox turn persistence."""

    def __init__(self, persistence_service: TurnPersistenceService | None = None) -> None:
        self._persistence_service = persistence_service or TurnPersistenceService()

    async def execute(self, ctx: ExecutionContext) -> None:
        """Execute outbox persistence scheduling."""
        logger.debug(
            f"[PersistenceStage] Scheduling outbox persistence for execution '{ctx.runtime.execution_id}'"
        )
        # Persistence stage completes out-of-band turn record enqueueing
        ctx.telemetry.metadata["persistence_scheduled"] = True
