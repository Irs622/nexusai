"""Middleware Pipeline architecture for cross-cutting request/response processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Sequence

from nexusai.core.annotations import stable
from nexusai.providers.models import ChatRequest, ChatResponse
from nexusai.providers.session import ProviderSession

# Type alias for downstream execution handler
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
    ) -> ChatResponse:
        """Process incoming ChatRequest and pass to next_call handler in pipeline.

        Args:
            request: Incoming ChatRequest payload.
            next_call: Next handler in middleware pipeline chain.
            session: Optional ProviderSession context.

        Returns:
            Processed ChatResponse payload.
        """
        ...


@stable
class MiddlewarePipeline:
    """Chain runner executing sequential middleware processing around provider requests."""

    def __init__(self, middlewares: Sequence[BaseMiddleware] | None = None) -> None:
        self._middlewares: list[BaseMiddleware] = list(middlewares or [])

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        """Append a middleware handler to the end of the pipeline."""
        self._middlewares.append(middleware)

    async def execute(
        self,
        request: ChatRequest,
        terminal_handler: NextHandler,
        session: ProviderSession | None = None,
    ) -> ChatResponse:
        """Execute the middleware chain wrapping around terminal_handler.

        Args:
            request: The ChatRequest to process.
            terminal_handler: Final handler executing provider chat call.
            session: Optional ProviderSession.

        Returns:
            Final ChatResponse returned by middleware chain.
        """
        chain: NextHandler = terminal_handler

        def _create_handler(mw: BaseMiddleware, nxt: NextHandler) -> NextHandler:
            async def handler(req: ChatRequest) -> ChatResponse:
                return await mw.process(req, nxt, session=session)

            return handler

        for middleware in reversed(self._middlewares):
            chain = _create_handler(middleware, chain)

        return await chain(request)
