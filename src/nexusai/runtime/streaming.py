"""Streaming Runtime for managing backpressure, partial token chunks, and stream cancellation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

from nexusai.core.annotations import stable
from nexusai.providers.models import ChatChoice, ChatMessage, ChatResponse, MessageRole, ToolCall
from nexusai.runtime.context import CancellationToken


@stable
@dataclass
class StreamChunk:
    """Partial streaming token chunk emitted during response generation."""

    delta_content: str = ""
    finish_reason: str | None = None
    tool_call_delta: list[ToolCall] | None = None
    index: int = 0


@stable
class StreamController:
    """Controller managing streaming iterations, cooperative cancellation, and stream assembly."""

    def __init__(self, cancellation_token: CancellationToken | None = None) -> None:
        self._cancellation_token = cancellation_token
        self._accumulated_content = ""
        self._finish_reason: str | None = None

    @property
    def accumulated_content(self) -> str:
        """Get total accumulated text content from stream chunks."""
        return self._accumulated_content

    async def wrap_stream(
        self, raw_stream: AsyncIterator[ChatResponse]
    ) -> AsyncIterator[ChatResponse]:
        """Wrap provider streaming generator to inject cancellation checks and accumulation."""
        async for chunk in raw_stream:
            if self._cancellation_token:
                self._cancellation_token.throw_if_cancelled()

            primary = chunk.primary_choice()
            if primary and primary.message and isinstance(primary.message.content, str):
                self._accumulated_content += primary.message.content
            if primary and primary.finish_reason:
                self._finish_reason = primary.finish_reason

            yield chunk

    def assemble_final_response(self, provider_id: str, model: str) -> ChatResponse:
        """Assemble accumulated stream chunks into a single canonical ChatResponse."""
        msg = ChatMessage(role=MessageRole.ASSISTANT, content=self._accumulated_content)
        choice = ChatChoice(index=0, message=msg, finish_reason=self._finish_reason or "stop")
        return ChatResponse(choices=[choice], model=model, provider=provider_id)
