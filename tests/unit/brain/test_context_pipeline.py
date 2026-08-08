"""
Unit tests for Milestone 3.1.3 Context & Token-Aware History Pipeline components.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from nexusai.brain.context import (
    ContextAssembler,
    InMemoryHistoryProvider,
    SystemPromptResolver,
)
from nexusai.brain.domain import (
    AssembledContext,
    ContextBudget,
    Message,
    MessageRole,
    SchemaVersion,
    Turn,
)
from nexusai.core.errors import BrainContextAssemblyError


def test_context_budget_invariants_and_serialization() -> None:
    """Verify ContextBudget invariants, available_history_tokens calculation, and serialization."""
    budget = ContextBudget(
        max_input_tokens=16000,
        reserved_output_tokens=4096,
        reserved_system_tokens=512,
        reserved_tool_tokens=0,
    )

    assert budget.available_history_tokens == 11392

    # Invariant: Invalid non-positive max_input_tokens
    with pytest.raises(BrainContextAssemblyError, match="max_input_tokens.*must be positive"):
        ContextBudget(max_input_tokens=-1)

    # Invariant: Reserved tokens exceed max_input_tokens
    with pytest.raises(
        BrainContextAssemblyError, match="available_history_tokens.*must be positive"
    ):
        ContextBudget(max_input_tokens=1000, reserved_output_tokens=2000)

    d = budget.to_dict()
    restored = ContextBudget.from_dict(d)
    assert restored == budget


def test_assembled_context_immutability_and_serialization() -> None:
    """Verify AssembledContext tuple immutability and serialization boundary."""
    ctx = AssembledContext(
        system_instruction="System prompt",
        history_messages=[
            Message(role=MessageRole.USER, content="Past query")
        ],  # Auto-converted to tuple
        user_message=Message(role=MessageRole.USER, content="Current query"),
        estimated_total_tokens=150,
        truncated_turn_count=2,
    )

    assert isinstance(ctx.history_messages, tuple)
    assert ctx.context_version == SchemaVersion(1, 0)
    assert ctx.truncated_turn_count == 2

    d = ctx.to_dict()
    restored = AssembledContext.from_dict(d)
    assert isinstance(restored.history_messages, tuple)
    assert restored.system_instruction == "System prompt"


def test_system_prompt_resolver_precedence() -> None:
    """Verify SystemPromptResolver precedence hierarchy (turn_override > session_default > global_default)."""
    resolver = SystemPromptResolver()

    # Precedence 1: Turn override takes top priority
    res1 = resolver.resolve(
        turn_override="Turn override prompt", session_default="Session default prompt"
    )
    assert res1 == "Turn override prompt"

    # Precedence 2: Session default takes second priority
    res2 = resolver.resolve(turn_override=None, session_default="Session default prompt")
    assert res2 == "Session default prompt"

    # Precedence 3: Fallback to global default
    res3 = resolver.resolve(turn_override=None, session_default=None)
    assert "NexusAI" in res3


@pytest.mark.asyncio
async def test_context_assembler_end_to_end() -> None:
    """Verify ContextAssembler orchestrates history loading, system prompt resolution, and truncation."""
    turn1 = Turn(
        user_message=Message(role=MessageRole.USER, content="What is Python?"),
        assistant_message=Message(
            role=MessageRole.ASSISTANT, content="Python is a programming language."
        ),
        token_usage={"total": 20},
    )
    turn2 = Turn(
        user_message=Message(role=MessageRole.USER, content="What is NexusAI?"),
        assistant_message=Message(
            role=MessageRole.ASSISTANT, content="NexusAI is an AI Operating System."
        ),
        token_usage={"total": 25},
    )

    provider = InMemoryHistoryProvider(turns=[turn1, turn2])
    assembler = ContextAssembler(history_provider=provider)
    conv_id = uuid4()
    budget = ContextBudget(max_input_tokens=10000, reserved_output_tokens=1000)

    ctx = await assembler.assemble(
        conversation_id=conv_id,
        user_content="Tell me more about it.",
        budget=budget,
        session_system_default="You are a helpful AI assistant.",
    )

    assert ctx.system_instruction == "You are a helpful AI assistant."
    assert ctx.user_message.content == "Tell me more about it."
    assert isinstance(ctx.history_messages, tuple)
    assert len(ctx.history_messages) >= 2
    assert ctx.estimated_total_tokens > 0
