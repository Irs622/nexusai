from __future__ import annotations

"""Unit tests for the NexusAI Provider SDK foundation."""

from typing import Any, AsyncIterator

import pytest

from nexusai.providers import (
    BaseProvider,
    Capability,
    CapabilityLevel,
    ChatChoice,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Embedding,
    EmbeddingResult,
    JSONSchema,
    MessageRole,
    ModelInfo,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderHealth,
    ProviderManager,
    ProviderMetadata,
    ProviderNotFoundError,
    ProviderRegistrationError,
    ProviderRegistry,
    ProviderRouter,
    ProviderSDKError,
    ToolSchema,
)


class DummyProvider(BaseProvider):
    """Concrete dummy implementation of BaseProvider for unit testing."""

    def __init__(
        self,
        provider_id: str = "dummy",
        display_name: str = "Dummy Provider",
        healthy: bool = True,
        supports_chat: bool = True,
        supports_vision: bool = False,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name
        self._healthy = healthy
        self.initialized = False
        self.shutdown_called = False
        caps: dict[Capability, CapabilityLevel] = {}
        if supports_chat:
            caps[Capability.CHAT] = CapabilityLevel.NATIVE
        if supports_vision:
            caps[Capability.VISION] = CapabilityLevel.ADVANCED

        self._capabilities = ProviderCapabilities(capabilities=caps)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self._provider_id,
            display_name=self._display_name,
            capabilities=self._capabilities,
        )

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True

    async def chat(self, request: ChatRequest) -> ChatResponse:
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Hello from DummyProvider",
        )
        choice = ChatChoice(index=0, message=msg, finish_reason="stop")
        return ChatResponse(choices=[choice], model="dummy-v1", provider=self.id)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]:
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Chunk",
        )
        choice = ChatChoice(index=0, message=msg)
        yield ChatResponse(choices=[choice], model="dummy-v1", provider=self.id)

    async def embeddings(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        embeds = [Embedding(text=t, vector=[0.1, 0.2], index=i) for i, t in enumerate(texts)]
        return EmbeddingResult(embeddings=embeds, model="dummy-embed", provider=self.id)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="dummy-v1", display_name="Dummy Model v1")]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy, latency_ms=10.0)


# ============================================================================
# Registry Tests
# ============================================================================


def test_provider_registration() -> None:
    registry = ProviderRegistry()
    provider = DummyProvider("openai", "OpenAI Provider")

    registry.register(provider)

    assert registry.get("openai") == provider
    assert "openai" in registry.list_provider_ids()
    meta_list = registry.list_providers()
    assert len(meta_list) == 1
    assert meta_list[0].provider_id == "openai"


def test_duplicate_registration_raises_error() -> None:
    registry = ProviderRegistry()
    provider1 = DummyProvider("openai", "OpenAI Provider 1")
    provider2 = DummyProvider("openai", "OpenAI Provider 2")

    registry.register(provider1)
    with pytest.raises(ProviderRegistrationError, match="already registered"):
        registry.register(provider2)


def test_provider_lookup_not_found_raises_error() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError, match="not registered"):
        registry.get("nonexistent")


def test_default_provider_management() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("p1")
    p2 = DummyProvider("p2")

    # First registration becomes default
    registry.register(p1)
    assert registry.get_default() == p1

    registry.register(p2)
    assert registry.get_default() == p1  # still p1

    # Explicit set_default
    registry.set_default("p2")
    assert registry.get_default() == p2


def test_unconfigured_default_raises_error() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderConfigurationError, match="No default provider"):
        registry.get_default()


def test_set_default_invalid_provider_raises_error() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError, match="not registered"):
        registry.set_default("unknown")


def test_provider_removal() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("p1")
    p2 = DummyProvider("p2")

    registry.register(p1)
    registry.register(p2)

    registry.unregister("p1")
    assert "p1" not in registry.list_provider_ids()
    assert registry.get_default() == p2

    with pytest.raises(ProviderNotFoundError, match="not registered"):
        registry.unregister("nonexistent")


# ============================================================================
# Manager Tests
# ============================================================================


@pytest.mark.asyncio
async def test_manager_lifecycle() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("p1")
    p2 = DummyProvider("p2")
    registry.register(p1)
    registry.register(p2)

    manager = ProviderManager(registry)
    await manager.initialize_all()
    assert p1.initialized is True
    assert p2.initialized is True

    await manager.shutdown_all()
    assert p1.shutdown_called is True
    assert p2.shutdown_called is True


@pytest.mark.asyncio
async def test_manager_health_check_all() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("healthy_p", healthy=True)
    p2 = DummyProvider("unhealthy_p", healthy=False)
    registry.register(p1)
    registry.register(p2)

    manager = ProviderManager(registry)
    health_map = await manager.health_check_all()

    assert health_map["healthy_p"].healthy is True
    assert health_map["unhealthy_p"].healthy is False

    healthy_list = await manager.healthy_providers()
    assert len(healthy_list) == 1
    assert healthy_list[0] == p1


def test_manager_capability_queries() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("chat_only", supports_chat=True, supports_vision=False)
    p2 = DummyProvider("vision_p", supports_chat=True, supports_vision=True)
    registry.register(p1)
    registry.register(p2)

    manager = ProviderManager(registry)

    vision_providers = manager.find_by_capability(Capability.VISION)
    assert len(vision_providers) == 1
    assert vision_providers[0] == p2

    assert manager.supports("vision_p", Capability.VISION) is True
    assert manager.supports("chat_only", Capability.VISION) is False


# ============================================================================
# Router Tests
# ============================================================================


@pytest.mark.asyncio
async def test_router_selection() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("p1", supports_vision=False)
    p2 = DummyProvider("p2", supports_vision=True)
    registry.register(p1)
    registry.register(p2)

    manager = ProviderManager(registry)
    router = ProviderRouter(manager)

    selected = await router.select_provider(required_capabilities={Capability.VISION})
    assert selected == p2


@pytest.mark.asyncio
async def test_router_no_match_raises_error() -> None:
    registry = ProviderRegistry()
    p1 = DummyProvider("unhealthy", healthy=False, supports_vision=True)
    registry.register(p1)

    manager = ProviderManager(registry)
    router = ProviderRouter(manager)

    with pytest.raises(ProviderNotFoundError, match="No healthy provider found"):
        await router.select_provider(required_capabilities={Capability.VISION})


# ============================================================================
# BaseProvider Async Context Manager Tests
# ============================================================================


@pytest.mark.asyncio
async def test_base_provider_async_context_manager() -> None:
    p = DummyProvider("context_p")
    async with p:
        assert p.initialized is True
        assert p.shutdown_called is False
    assert p.shutdown_called is True


# ============================================================================
# Data Models Tests
# ============================================================================


def test_chat_response_primary_choice() -> None:
    msg = ChatMessage(role=MessageRole.USER, content="hi")
    choice = ChatChoice(index=0, message=msg)
    response = ChatResponse(choices=[choice])

    assert response.primary_choice() == choice
    assert response.best_choice() == choice

    empty_response = ChatResponse(choices=[])
    with pytest.raises(ProviderSDKError, match="contains no choices"):
        empty_response.primary_choice()


def test_json_schema_model() -> None:
    js = JSONSchema(schema={"type": "object", "properties": {"a": {"type": "string"}}}, strict=True)
    assert js.strict is True
    assert js.schema["type"] == "object"

    tool = ToolSchema(name="my_tool", description="Test tool", parameters=js)
    assert tool.parameters.strict is True


def test_provider_profile_cache() -> None:
    from nexusai.providers import ProviderProfile, ProviderProfileCache
    from nexusai.providers.models import ProviderMetadata

    cache = ProviderProfileCache()
    meta = ProviderMetadata(provider_id="openrouter", display_name="OpenRouter")
    prof = ProviderProfile(metadata=meta)
    cache.set(prof)

    fetched = cache.get("openrouter")
    assert fetched is not None
    assert fetched.provider_id == "openrouter"
    assert len(cache.list_profiles()) == 1

    cache.clear()
    assert cache.get("openrouter") is None


@pytest.mark.asyncio
async def test_provider_policy_routing() -> None:
    from nexusai.providers import CapabilityPolicy

    registry = ProviderRegistry()
    p1 = DummyProvider("p1", supports_vision=False)
    p2 = DummyProvider("p2", supports_vision=True)
    registry.register(p1)
    registry.register(p2)

    manager = ProviderManager(registry)
    router = ProviderRouter(manager)

    policy = CapabilityPolicy(required_capabilities={Capability.VISION})
    routed = await router.route(policy=policy)
    assert routed == p2


def test_provider_runtime_metrics_ewma() -> None:
    from nexusai.providers import ProviderRuntimeMetrics

    metrics = ProviderRuntimeMetrics(alpha=0.5)
    metrics.record_success(100.0)
    assert metrics.ewma_latency_ms == 100.0
    assert metrics.success_rate == 1.0

    metrics.record_success(200.0)
    assert metrics.ewma_latency_ms == 150.0
    assert len(metrics.rolling_latencies) == 2

    metrics.record_error("timeout")
    assert metrics.error_count == 1
    assert metrics.last_error == "timeout"


@pytest.mark.asyncio
async def test_health_monitor_service() -> None:
    from nexusai.providers import HealthMonitor

    registry = ProviderRegistry()
    p1 = DummyProvider("p1", healthy=True)
    registry.register(p1)

    monitor = HealthMonitor(registry)
    health = await monitor.check_provider("p1")
    assert health.healthy is True
    assert monitor.is_healthy("p1") is True


@pytest.mark.asyncio
async def test_middleware_pipeline() -> None:
    from nexusai.providers import BaseMiddleware, MiddlewarePipeline, ProviderSession

    execution_order: list[str] = []

    class TestMiddleware(BaseMiddleware):
        def __init__(self, name: str) -> None:
            self.name = name

        async def process(
            self, request: ChatRequest, next_call, session: ProviderSession | None = None
        ) -> ChatResponse:
            execution_order.append(f"enter_{self.name}")
            resp = await next_call(request)
            execution_order.append(f"exit_{self.name}")
            return resp

    pipeline = MiddlewarePipeline([TestMiddleware("m1"), TestMiddleware("m2")])

    async def terminal_call(req: ChatRequest) -> ChatResponse:
        execution_order.append("terminal")
        return ChatResponse(choices=[])

    req = ChatRequest(messages=[])
    await pipeline.execute(req, terminal_call)

    assert execution_order == ["enter_m1", "enter_m2", "terminal", "exit_m2", "exit_m1"]


def test_provider_session() -> None:
    from nexusai.providers import ProviderSession

    session = ProviderSession(conversation_id="conv_123")
    session.set_tool_state("browser_tab", "tab_1")

    assert session.conversation_id == "conv_123"
    assert session.get_tool_state("browser_tab") == "tab_1"


def test_execution_context_and_cancellation() -> None:
    from nexusai.providers import ExecutionContext, ExecutionHandle, ProviderTimeoutError

    ctx = ExecutionContext()
    token = ctx.runtime.cancellation_token
    assert not token.is_cancelled

    handle = ExecutionHandle(task_id="t1", context=ctx)
    handle.cancel("User aborted")
    assert token.is_cancelled
    assert token.reason == "User aborted"

    with pytest.raises(ProviderTimeoutError, match="User aborted"):
        token.throw_if_cancelled()


@pytest.mark.asyncio
async def test_circuit_breaker() -> None:
    from nexusai.providers import CircuitBreaker, CircuitState, ProviderCircuitOpenError

    cb = CircuitBreaker("p1", failure_threshold=2, recovery_timeout_seconds=60.0)
    assert cb.state == CircuitState.CLOSED

    cb.record_failure(ValueError("err1"))
    assert cb.state == CircuitState.CLOSED

    cb.record_failure(ValueError("err2"))
    assert cb.state == CircuitState.OPEN

    async def dummy():
        return "ok"

    with pytest.raises(ProviderCircuitOpenError, match="is OPEN"):
        await cb.call(dummy)


@pytest.mark.asyncio
async def test_retry_middleware() -> None:
    from nexusai.providers import ProviderTimeoutError, RetryMiddleware, RetryPolicy

    policy = RetryPolicy(max_retries=2, initial_delay_seconds=0.01)
    middleware = RetryMiddleware(policy)

    attempts = 0

    async def flaky_call(req: ChatRequest) -> ChatResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ProviderTimeoutError("Request timeout")
        return ChatResponse(choices=[])

    req = ChatRequest(messages=[])
    res = await middleware.process(req, flaky_call)
    assert res is not None
    assert attempts == 2


def test_hierarchical_cancellation_token() -> None:
    from nexusai.providers import CancellationToken

    parent = CancellationToken()
    child = parent.create_child()

    assert not parent.is_cancelled
    assert not child.is_cancelled

    parent.cancel("Parent stop")
    assert parent.is_cancelled
    assert child.is_cancelled


def test_test_clock_and_deadline() -> None:
    from datetime import datetime, timezone

    from nexusai.providers import Deadline, TestClock

    clock = TestClock(initial_time=1000.0)
    deadline_at = datetime.fromtimestamp(1010.0, tz=timezone.utc)
    deadline = Deadline(deadline_at=deadline_at, clock=clock)

    assert deadline.remaining_seconds() == 10.0
    assert deadline.is_expired() is False

    clock.advance(15.0)
    assert deadline.is_expired() is True


def test_execution_state_machine() -> None:
    from nexusai.providers import ExecutionState, ExecutionStateMachine, ProviderSDKError

    sm = ExecutionStateMachine(ExecutionState.CREATED)
    assert sm.current_state == ExecutionState.CREATED

    sm.transition_to(ExecutionState.QUEUED)
    assert sm.current_state == ExecutionState.QUEUED

    sm.transition_to(ExecutionState.RUNNING)
    assert sm.current_state == ExecutionState.RUNNING

    with pytest.raises(ProviderSDKError, match="Invalid state transition"):
        sm.transition_to(ExecutionState.CREATED)


@pytest.mark.asyncio
async def test_execution_engine_pipeline() -> None:
    from nexusai.providers import ExecutionEngine, MockProvider

    p = MockProvider("engine_mock")
    engine = ExecutionEngine()
    engine.manager.registry.register(p)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="hello engine")])
    res = await engine.execute_chat(req)

    assert res is not None
    assert res.primary_choice().message.content == "Mock response output"
    assert res.provider == "engine_mock"
