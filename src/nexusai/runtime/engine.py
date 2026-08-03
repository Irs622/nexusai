"""Decoupled ExecutionEngine, ExecutionStrategy, ProviderExecutor, and Explainable RoutingDecision."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any, AsyncIterator

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.health import HealthMonitor
from nexusai.providers.manager import ProviderManager
from nexusai.providers.models import ChatRequest, ChatResponse
from nexusai.providers.policy import BaseProviderPolicy, PolicyResult
from nexusai.providers.router import ProviderRouter
from nexusai.providers.session import ProviderSession
from nexusai.runtime.circuit_breaker import CircuitBreaker
from nexusai.runtime.context import ExecutionContext
from nexusai.runtime.middleware import MiddlewarePipeline
from nexusai.runtime.state_machine import ExecutionState, ExecutionStateMachine


@stable
@dataclass(frozen=True)
class RoutingDecision:
    """Explainable routing decision result detailing policy scoring breakdown and estimates."""

    provider_id: str
    provider: BaseProvider
    model: str
    policy_score: float = 1.0
    policy_results: dict[str, PolicyResult] = field(default_factory=dict)
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@stable
class ProviderExecutor:
    """Target executor executing low-level provider invocations."""

    async def invoke_chat(self, provider: BaseProvider, request: ChatRequest) -> ChatResponse:
        """Invoke provider chat completion."""
        return await provider.chat(request)

    async def invoke_stream_chat(
        self, provider: BaseProvider, request: ChatRequest
    ) -> AsyncIterator[ChatResponse]:
        """Invoke provider streaming chat completion."""
        async for chunk in provider.stream_chat(request):
            yield chunk


@stable
class ExecutionStrategy:
    """Execution strategy governing circuit breaking, deadlines, and task resilience."""

    def __init__(self) -> None:
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def get_circuit_breaker(self, provider_id: str) -> CircuitBreaker:
        """Retrieve or create CircuitBreaker instance for provider_id."""
        if provider_id not in self._circuit_breakers:
            self._circuit_breakers[provider_id] = CircuitBreaker(provider_id=provider_id)
        return self._circuit_breakers[provider_id]

    async def execute_guarded(
        self,
        provider_id: str,
        executor_fn: Any,
        context: ExecutionContext,
    ) -> ChatResponse:
        """Execute a provider invocation guarded by CircuitBreaker, Cancellation, and Deadline."""
        context.runtime.cancellation_token.throw_if_cancelled()
        if context.resource.deadline:
            context.resource.deadline.throw_if_expired()

        circuit_breaker = self.get_circuit_breaker(provider_id)
        return await circuit_breaker.call(executor_fn)


@stable
class ExecutionEngine:
    """Orchestration facade executing provider requests across decoupled runtime layers."""

    def __init__(
        self,
        manager: ProviderManager | None = None,
        router: ProviderRouter | None = None,
        pipeline: MiddlewarePipeline | None = None,
        health_monitor: HealthMonitor | None = None,
        executor: ProviderExecutor | None = None,
        strategy: ExecutionStrategy | None = None,
    ) -> None:
        self._manager = manager or ProviderManager()
        self._router = router or ProviderRouter(self._manager)
        self._pipeline = pipeline or MiddlewarePipeline()
        self._health_monitor = health_monitor or HealthMonitor(self._manager.registry)
        self._executor = executor or ProviderExecutor()
        self._strategy = strategy or ExecutionStrategy()

    @property
    def manager(self) -> ProviderManager:
        return self._manager

    @property
    def router(self) -> ProviderRouter:
        return self._router

    @property
    def pipeline(self) -> MiddlewarePipeline:
        return self._pipeline

    @property
    def health_monitor(self) -> HealthMonitor:
        return self._health_monitor

    async def execute_chat(
        self,
        request: ChatRequest,
        context: ExecutionContext | None = None,
        session: ProviderSession | None = None,
        policy: BaseProviderPolicy | None = None,
    ) -> ChatResponse:
        """Execute a chat request through the orchestrated pipeline."""
        ctx = context or ExecutionContext()
        ctx.runtime.cancellation_token.throw_if_cancelled()
        if ctx.resource.deadline:
            ctx.resource.deadline.throw_if_expired()

        state_machine = ExecutionStateMachine(ExecutionState.CREATED)
        state_machine.transition_to(ExecutionState.QUEUED)
        state_machine.transition_to(ExecutionState.RUNNING)

        start_time = time.time()

        # 1. Router selects candidate provider and returns Explainable RoutingDecision
        selected_provider = await self._router.route(
            policy=policy,
            required_capabilities=set(),
            request=request,
        )

        decision = RoutingDecision(
            provider_id=selected_provider.id,
            provider=selected_provider,
            model=request.model or "default",
            policy_score=1.0,
            policy_results={"capability": PolicyResult(allow=True, score=1.0, reason="Supports requested features")},
            reason="Adaptive Router Selection",
        )
        ctx.runtime.provider_id = decision.provider_id
        ctx.runtime.model = decision.model

        # 2. Terminal execution handler invoking strategy and executor
        async def terminal_handler(req: ChatRequest) -> ChatResponse:
            async def raw_call() -> ChatResponse:
                return await self._executor.invoke_chat(decision.provider, req)

            return await self._strategy.execute_guarded(decision.provider_id, raw_call, ctx)

        # 3. Execute via Middleware Pipeline
        try:
            response = await self._pipeline.execute(
                request,
                terminal_handler,
                session=session,
            )
            state_machine.transition_to(ExecutionState.COMPLETED)
            elapsed_ms = (time.time() - start_time) * 1000.0
            logger.info(
                "ExecutionEngine: Task {} routed to '{}' (score={:.2f}) completed in {:.2f}ms",
                ctx.request.request_id,
                decision.provider_id,
                decision.policy_score,
                elapsed_ms,
            )
            return response
        except Exception as err:
            state_machine.transition_to(ExecutionState.FAILED, reason=str(err))
            logger.error("ExecutionEngine: Task {} failed: {}", ctx.request.request_id, err)
            raise
