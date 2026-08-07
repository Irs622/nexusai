"""
Unit tests for Milestone 3.1.4 Canonical Prompt Pipeline & Priority ExtensionEvent Engine.
"""

from __future__ import annotations

import pytest

from nexusai.brain.domain import (
    AssembledContext,
    MessageRole,
    PromptBundle,
    PromptMessage,
    SchemaVersion,
    TextArtifact,
)
from nexusai.brain.plugins import ExtensionEvent, PriorityExtensionDispatcher
from nexusai.brain.prompt import PromptRenderer
from nexusai.brain.runtime import ExecutionContext


def test_prompt_renderer_canonical_bundle_rendering() -> None:
    """Verify PromptRenderer compiles AssembledContext into a provider-independent PromptBundle."""
    renderer = PromptRenderer()

    assembled = AssembledContext(
        system_instruction="You are a helpful AI OS.",
        history_messages=(
            PromptMessage(role=MessageRole.USER, content="Hello"),
            PromptMessage(role=MessageRole.ASSISTANT, content="Hi there"),
        ),
        user_message=PromptMessage(role=MessageRole.USER, content="How are you?"),
        estimated_total_tokens=50,
    )

    artifact = TextArtifact(text="Attachment text")
    bundle = renderer.render(context=assembled, artifacts=[artifact])

    assert isinstance(bundle, PromptBundle)
    assert bundle.bundle_version == SchemaVersion(1, 0)
    assert len(bundle.messages) == 4  # System + 2 History + User
    assert bundle.messages[0].role == MessageRole.SYSTEM
    assert bundle.messages[0].content == "You are a helpful AI OS."
    assert bundle.messages[1].role == MessageRole.USER
    assert bundle.messages[2].role == MessageRole.ASSISTANT
    assert bundle.messages[3].role == MessageRole.USER
    assert len(bundle.artifacts) == 1
    assert isinstance(bundle.artifacts[0], TextArtifact)


@pytest.mark.asyncio
async def test_priority_extension_dispatcher_ordering() -> None:
    """Verify PriorityExtensionDispatcher dispatches event handlers in integer priority order (ascending)."""
    dispatcher = PriorityExtensionDispatcher()
    execution_order: list[str] = []

    async def audit_handler(event: ExtensionEvent) -> None:
        execution_order.append(f"Audit(priority={event.priority})")

    async def safety_handler(event: ExtensionEvent) -> None:
        execution_order.append(f"Safety(priority={event.priority})")

    async def tracing_handler(event: ExtensionEvent) -> None:
        execution_order.append(f"Tracing(priority={event.priority})")

    # Register handlers out of order
    dispatcher.register_handler("before_provider_invocation", tracing_handler, priority=100)
    dispatcher.register_handler("before_provider_invocation", audit_handler, priority=1)
    dispatcher.register_handler("before_provider_invocation", safety_handler, priority=10)

    ctx = ExecutionContext()
    event = ExtensionEvent(event_name="before_provider_invocation", context=ctx)
    await dispatcher.dispatch(event)

    # Must execute in priority order: 1 -> 10 -> 100
    assert execution_order == [
        "Audit(priority=1)",
        "Safety(priority=10)",
        "Tracing(priority=100)",
    ]
