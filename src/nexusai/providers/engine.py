"""Single official ExecutionEngine entry point for NexusAI runtime processing."""

from __future__ import annotations

import time
from typing import cast

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.circuit_breaker import CircuitBreaker
from nexusai.providers.context import ExecutionContext
from nexusai.providers.health import HealthMonitor
from nexusai.providers.manager import ProviderManager
from nexusai.providers.middleware import MiddlewarePipeline
from nexusai.providers.models import ChatRequest, ChatResponse
from nexusai.providers.policy import BaseProviderPolicy
from nexusai.providers.router import ProviderRouter
from nexusai.providers.session import ProviderSession
from nexusai.providers.state_machine import ExecutionState, ExecutionStateMachine


@stable
class ExecutionEngine:
    """Single official entry point for executing provider requests through the runtime pipeline.

    Pipeline sequence:
    Application -> ExecutionEngine -> ExecutionContext -> MiddlewarePipeline ->
    ProviderRouter -> CircuitBreaker -> BaseProvider -> ChatResponse -> Events & Metrics
    """

    def __init__(
        self,
        manager: ProviderManager | None = None,
        router: ProviderRouter | None = None,
        pipeline: MiddlewarePipeline | None = None,
        health_monitor: HealthMonitor | None = None,
    ) -> None:
        self._manager = manager or ProviderManager()
        self._router = router or ProviderRouter(self._manager)
        self._pipeline = pipeline or MiddlewarePipeline()
        self._health_monitor = health_monitor or HealthMonitor(self._manager.registry)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

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

    def _get_circuit_breaker(self, provider_id: str) -> CircuitBreaker:
        if provider_id not in self._circuit_breakers:
            self._circuit_breakers[provider_id] = CircuitBreaker(provider_id=provider_id)
        return self._circuit_breakers[provider_id]

    async def execute_chat(
        self,
        request: ChatRequest,
        context: ExecutionContext | None = None,
        session: ProviderSession | None = None,
        policy: BaseProviderPolicy | None = None,
    ) -> ChatResponse:
        """Execute a chat completion request through the unified runtime pipeline.

        Args:
            request: Strongly-typed ChatRequest.
            context: Rich ExecutionContext (tracing, cancellation, budget).
            session: Stateful ProviderSession context.
            policy: ProviderPolicy for candidate selection.

        Returns:
            Strongly-typed ChatResponse.
        """
        ctx = context or ExecutionContext()
        ctx.runtime.cancellation_token.throw_if_cancelled()
        if ctx.resource.deadline:
            ctx.resource.deadline.throw_if_expired()

        state_machine = ExecutionStateMachine(ExecutionState.CREATED)
        state_machine.transition_to(ExecutionState.QUEUED)
        state_machine.transition_to(ExecutionState.RUNNING)

        start_time = time.time()

        # 1. Route provider candidate using policy
        selected_provider = await self._router.route(
            policy=policy,
            required_capabilities=set(),
            request=request,
        )
        ctx.runtime.provider_id = selected_provider.id
        ctx.runtime.model = request.model or "default"

        circuit_breaker = self._get_circuit_breaker(selected_provider.id)

        # 2. Terminal execution handler wrapped inside circuit breaker
        async def terminal_handler(req: ChatRequest) -> ChatResponse:
            ctx.runtime.cancellation_token.throw_if_cancelled()

            async def raw_call() -> ChatResponse:
                return await selected_provider.chat(req)

            res = await circuit_breaker.call(raw_call)
            return cast(ChatResponse, res)

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
                "ExecutionEngine: Executed chat request {} via provider '{}' in {:.2f}ms",
                ctx.request.request_id,
                selected_provider.id,
                elapsed_ms,
            )
            return response
        except Exception as err:
            state_machine.transition_to(ExecutionState.FAILED, reason=str(err))
            logger.error("ExecutionEngine: Task {} failed: {}", ctx.request.request_id, err)
            raise
