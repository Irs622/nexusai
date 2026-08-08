"""
TurnStream async iterator wrapper providing direct delta token streaming and backpressure.
"""

from __future__ import annotations

from typing import AsyncIterator

from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.metrics import TurnChunk
from nexusai.brain.telemetry.tracer import ExecutionTracer
from nexusai.core.errors import BrainError
from nexusai.logging.logger import logger


class TurnStream:
    """Async iterator wrapper pipelining provider token streams directly to caller iterators."""

    def __init__(
        self,
        provider_stream: AsyncIterator[TurnChunk],
        context: ExecutionContext,
        tracer: ExecutionTracer | None = None,
    ) -> None:
        """Initialize TurnStream iterator wrapper.

        Args:
            provider_stream: Downstream provider AsyncIterator[TurnChunk].
            context: ExecutionContext transport container.
            tracer: Telemetry tracer for TTFT and latency markers.
        """
        self._provider_stream = provider_stream
        self._ctx = context
        self._tracer = tracer or ExecutionTracer()
        self._accumulated_text: list[str] = []
        self._chunk_count: int = 0

    @property
    def full_text(self) -> str:
        """Get accumulated full response text."""
        return "".join(self._accumulated_text)

    @property
    def chunk_count(self) -> int:
        """Get total number of chunks yielded."""
        return self._chunk_count

    def __aiter__(self) -> AsyncIterator[TurnChunk]:
        return self._stream_generator()

    async def _stream_generator(self) -> AsyncIterator[TurnChunk]:
        """Internal async generator iterating provider chunks with zero double-buffering."""
        self._tracer.mark_provider_connected()

        try:
            async for chunk in self._provider_stream:
                # 1. Check for cancellation signal
                if self._ctx.cancellation.is_cancelled:
                    self._tracer.is_cancelled = True
                    logger.warning("TurnStream aborted due to client cancellation signal")
                    raise BrainError("Turn stream aborted by cancellation signal.")

                # 2. Capture Time To First Token (TTFT) marker on first chunk
                if self._chunk_count == 0:
                    self._tracer.mark_first_chunk()

                # 3. Track text and chunk sequence
                self._chunk_count += 1
                if chunk.delta:
                    self._accumulated_text.append(chunk.delta)
                    self._ctx.usage.add_output_tokens(len(chunk.delta) // 4 + 1)
                    self._tracer.output_tokens = self._ctx.usage.used_output_tokens

                # 4. Pipeline chunk directly to client (Zero double-buffering)
                yield chunk

            # Mark stream completion
            self._tracer.mark_last_chunk()

        except Exception as e:
            if not self._ctx.cancellation.is_cancelled and not isinstance(e, BrainError):
                logger.error(f"Error encountered during TurnStream iteration: {e}")
            raise
