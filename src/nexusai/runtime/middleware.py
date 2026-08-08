"""Middleware Pipeline architecture for cross-cutting request/response processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Sequence

from nexusai.core.annotations import stable
from nexusai.providers.models import ChatRequest, ChatResponse
from nexusai.providers.session import ProviderSession

NextHandler = Callable[[ChatRequest], Awaitable[ChatResponse]]


@stable
class BaseMiddleware(ABC):
    """Abstract Base Class for provider middleware extensions (Logging, Tracing, Retry, Cost)."""

    @abstractmethod
    async def process(
        self,
        request: ChatRequest,
        next_call: NextHandler,
        session: ProviderSession | None = None,
    ) -> ChatResponse: ...


@stable
class MiddlewarePipeline:
    """Chain runner executing sequential middleware processing around provider requests."""

    def __init__(self, middlewares: Sequence[BaseMiddleware] | None = None) -> None:
        self._middlewares: list[BaseMiddleware] = list(middlewares or [])

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        self._middlewares.append(middleware)

    async def execute(
        self,
        request: ChatRequest,
        terminal_handler: NextHandler,
        session: ProviderSession | None = None,
    ) -> ChatResponse:
        chain = terminal_handler
        for middleware in reversed(self._middlewares):
            current_mw = middleware
            current_next = chain

            async def make_call(
                req: ChatRequest, mw: BaseMiddleware = current_mw, nxt: NextHandler = current_next
            ) -> ChatResponse:
                return await mw.process(req, nxt, session=session)

            chain = make_call

        return await chain(request)
