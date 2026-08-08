"""
Unit tests for nexusai.brain.runtime models, ExecutionContext sub-contexts, invariants, and DAG topology.
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError

import pytest

import nexusai.brain.runtime.context as ctx_module
from nexusai.brain.runtime import (
    CancellationContext,
    ExecutionBudget,
    ExecutionContext,
    ExecutionFeatures,
    ExecutionMode,
    ExecutionUsage,
    IdentityContext,
    ModelCapabilities,
    RuntimeContext,
    SecurityContext,
    SessionState,
    TelemetryContext,
    TurnChunk,
    TurnMetrics,
)
from nexusai.core.errors import BrainContextAssemblyError


def test_model_capabilities_invariants() -> None:
    """Verify ModelCapabilities constructor invariant validation."""
    caps = ModelCapabilities(max_input_tokens=8192, max_output_tokens=1024, reserved_tokens=256)
    assert caps.max_input_tokens == 8192

    with pytest.raises(BrainContextAssemblyError, match="must be positive"):
        ModelCapabilities(max_input_tokens=0, max_output_tokens=1024)

    with pytest.raises(BrainContextAssemblyError, match="cannot be negative"):
        ModelCapabilities(max_input_tokens=100, max_output_tokens=100, reserved_tokens=-1)


def test_execution_budget_invariants_and_serialization() -> None:
    """Verify ExecutionBudget constructor invariants, immutability, and serialization boundaries."""
    budget = ExecutionBudget(max_input_tokens=16000, max_output_tokens=2000, max_time_ms=5000.0)
    assert budget.max_input_tokens == 16000

    # Constructor invariant validation
    with pytest.raises(BrainContextAssemblyError, match="must be positive"):
        ExecutionBudget(max_input_tokens=-1)

    with pytest.raises(BrainContextAssemblyError, match="must be positive"):
        ExecutionBudget(max_output_tokens=0)

    with pytest.raises(FrozenInstanceError):
        budget.max_input_tokens = 32000  # type: ignore[misc]

    d = budget.to_dict()
    restored = ExecutionBudget.from_dict(d)
    assert restored == budget


def test_execution_usage_accumulation_and_serialization() -> None:
    """Verify ExecutionUsage counter accumulation, negative token protection, and serialization."""
    usage = ExecutionUsage()
    usage.add_input_tokens(50)
    usage.add_output_tokens(25)
    assert usage.total_tokens == 75

    with pytest.raises(ValueError, match="cannot be negative"):
        usage.add_input_tokens(-10)

    d = usage.to_dict()
    restored = ExecutionUsage.from_dict(d)
    assert restored.total_tokens == 75


def test_session_state_and_execution_mode() -> None:
    """Verify SessionState mutable configuration and ExecutionMode / Features."""
    state = SessionState(
        provider_id="openrouter",
        active_model="anthropic/claude-3.5-sonnet",
        execution_mode=ExecutionMode.CHAT,
        execution_features=ExecutionFeatures(streaming=True, reasoning=True),
    )

    assert state.provider_id == "openrouter"
    assert state.execution_features.reasoning is True
    assert state.turn_count == 0

    state.turn_count += 1
    assert state.turn_count == 1


def test_execution_context_topology() -> None:
    """Verify ExecutionContext sub-context DAG dependency structure."""
    identity = IdentityContext(user_id="user_123", workspace_id="ws_456")
    runtime = RuntimeContext(required_capabilities=["vision", "128k"])
    security = SecurityContext(permissions=["read", "execute"], roles=["admin"])
    telemetry = TelemetryContext()
    cancellation = CancellationContext()

    ctx = ExecutionContext(
        identity=identity,
        runtime=runtime,
        security=security,
        telemetry=telemetry,
        cancellation=cancellation,
    )

    assert ctx.identity.user_id == "user_123"
    assert ctx.runtime.required_capabilities == ["vision", "128k"]
    assert ctx.security.permissions == ["read", "execute"]
    assert ctx.cancellation.is_cancelled is False

    ctx.cancellation.is_cancelled = True
    assert ctx.cancellation.is_cancelled is True


def test_turn_metrics_serialization_and_chunk() -> None:
    """Verify TurnMetrics immutable telemetry model, serialization, and TurnChunk streaming unit."""
    metrics = TurnMetrics(
        latency_ms=120.5,
        ttft_ms=35.0,
        tokens_per_second=45.2,
        input_tokens=100,
        output_tokens=50,
    )
    assert metrics.ttft_ms == 35.0
    assert metrics.input_tokens == 100

    d = metrics.to_dict()
    restored = TurnMetrics.from_dict(d)
    assert restored == metrics

    chunk = TurnChunk(delta="Hello", finish_reason=None, sequence=0)
    assert chunk.delta == "Hello"
    assert chunk.sequence == 0

    chunk_dict = chunk.to_dict()
    restored_chunk = TurnChunk.from_dict(chunk_dict)
    assert restored_chunk == chunk


def test_no_circular_context_dependencies() -> None:
    """Verify context module does not have circular or invalid sub-context cross-references."""
    classes = [
        ctx_module.IdentityContext,
        ctx_module.RuntimeContext,
        ctx_module.SecurityContext,
        ctx_module.TelemetryContext,
        ctx_module.CancellationContext,
    ]

    for cls in classes:
        sig = inspect.signature(cls)
        for param in sig.parameters.values():
            annotation_str = str(param.annotation)
            # Sub-contexts must not reference ExecutionContext parent
            assert "ExecutionContext" not in annotation_str
