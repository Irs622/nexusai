"""
PromptRenderer service transforming AssembledContext into canonical PromptBundle v1.0.
"""

from __future__ import annotations

from typing import Any

from nexusai.brain.domain.artifacts import Artifact
from nexusai.brain.domain.context import AssembledContext
from nexusai.brain.domain.prompt import MessageRole, PromptBundle, PromptMessage
from nexusai.brain.domain.version import SchemaVersion
from nexusai.logging.logger import logger


class PromptRenderer:
    """Renders AssembledContext into provider-agnostic canonical PromptBundle containers."""

    def render(
        self,
        context: AssembledContext,
        artifacts: list[Artifact] | tuple[Artifact, ...] | None = None,
        options: dict[str, Any] | None = None,
    ) -> PromptBundle:
        """Render AssembledContext into a canonical PromptBundle.

        CRITICAL ARCHITECTURAL BOUNDARY:
        PromptRenderer ONLY builds provider-independent PromptBundle instances.
        Vendor-specific formatting (e.g. ChatML, Claude XML blocks, Gemini parts)
        MUST strictly occur downstream within ProviderRuntime adapters.

        Args:
            context: The assembled context payload.
            artifacts: Optional multimodal artifacts to attach.
            options: Optional prompt options.

        Returns:
            An immutable canonical PromptBundle.
        """
        logger.debug(
            "Rendering canonical PromptBundle",
            extra={
                "history_message_count": len(context.history_messages),
                "has_system_instruction": context.system_instruction is not None,
            },
        )

        messages_list: list[PromptMessage] = []

        # 1. Include system prompt as system message if present
        if context.system_instruction:
            messages_list.append(
                PromptMessage(role=MessageRole.SYSTEM, content=context.system_instruction)
            )

        # 2. Append history messages
        messages_list.extend(context.history_messages)

        # 3. Append current user message
        if context.user_message and context.user_message.content:
            messages_list.append(context.user_message)

        art_tuple: tuple[Artifact, ...] = tuple(artifacts) if artifacts else ()

        bundle = PromptBundle(
            bundle_version=SchemaVersion(1, 0),
            system_instruction=context.system_instruction,
            messages=tuple(messages_list),
            artifacts=art_tuple,
            options=options or {},
        )

        logger.info(f"Canonical PromptBundle rendered with {len(bundle.messages)} total messages")
        return bundle
