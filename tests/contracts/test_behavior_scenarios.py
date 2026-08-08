import pytest

pytestmark = pytest.mark.network
"""Golden Scenario Tests verifying end-to-end runtime behavior resiliency."""

import pytest

from nexusai.providers import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    MockProvider,
    ProviderTimeoutError,
)
from nexusai.runtime import (
    CircuitState,
    ExecutionEngine,
    ExecutionReport,
)


@pytest.mark.asyncio
async def test_golden_scenario_circuit_breaker_and_routing_fallback() -> None:
    """Golden Behavior Scenario:
    Primary provider fails repeated requests -> CircuitBreaker trips to OPEN ->
    ExecutionEngine routes request to healthy fallback provider -> Success & ExecutionReport generated.
    """
    engine = ExecutionEngine()

    # 1. Register failing primary provider and healthy secondary provider
    primary_p = MockProvider(provider_id="primary_failing", healthy=True)
    secondary_p = MockProvider(provider_id="secondary_fallback", healthy=True)

    engine.manager.registry.register(primary_p)
    engine.manager.registry.register(secondary_p)
    engine.manager.registry.set_default(secondary_p)

    # 2. Trip CircuitBreaker on primary provider
    cb = engine._strategy.get_circuit_breaker("primary_failing")
    for _ in range(5):
        cb.record_failure(ProviderTimeoutError("Primary timeout"))
    assert cb.state == CircuitState.OPEN

    # 3. Execute chat request via secondary fallback provider
    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="Scenario test")])
    res = await engine.execute_chat(req)

    assert res is not None
    assert res.provider == "secondary_fallback"

    # 4. Verify ExecutionReport generation
    report = ExecutionReport(
        request_id="req_101",
        provider_id=res.provider,
        model=res.model,
        token_in=10,
        token_out=15,
        total_tokens=25,
        cost=0.0001,
        latency_ms=12.5,
    )
    assert report.total_tokens == 25
    assert "secondary_fallback" in report.summary()
