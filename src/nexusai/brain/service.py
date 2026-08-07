"""
BrainRuntimeFacade entry point service for single-turn execution orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Any
from uuid import UUID

from nexusai.brain.domain.session import BrainSession
from nexusai.brain.domain.turn import Message, MessageRole, Turn
from nexusai.brain.pipeline.pipeline import ExecutionPipeline
from nexusai.brain.runtime.context import (
    CancellationContext,
    ExecutionContext,
    IdentityContext,
    RuntimeContext,
    SecurityContext,
    TelemetryContext,
)
from nexusai.brain.runtime.metrics import TurnChunk, TurnMetrics
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.streaming.stream import TurnStream
from nexusai.brain.telemetry.tracer import ExecutionTracer
from nexusai.logging.logger import logger


@dataclass(frozen=True)
class TurnResponse:
    """Synchronous single-turn response container.

    Attributes:
        turn: Completed Turn aggregate entity.
        metrics: Diagnostic TurnMetrics telemetry object.
        raw_response_text: Full response text.
    """

    turn: Turn
    metrics: TurnMetrics
    raw_response_text: str = ""


class BrainRuntimeFacade:
    """Primary public entry point facade for single-turn Brain Runtime orchestration."""

    def __init__(self, pipeline: ExecutionPipeline | None = None) -> None:
        """Initialize BrainRuntimeFacade with an optional ExecutionPipeline.

        Args:
            pipeline: ExecutionPipeline orchestrator (defaults to standard pipeline).
        """
        self._pipeline = pipeline or ExecutionPipeline()

    def create_context(
        self,
        session: BrainSession,
        state: SessionState,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ExecutionContext:
        """Construct a unified ExecutionContext transport container for a turn execution.

        Args:
            session: Immutable BrainSession identity context.
            state: Mutable SessionState configuration.
            user_id: Optional user ID.
            workspace_id: Optional workspace ID.

        Returns:
            An ExecutionContext container.
        """
        identity = IdentityContext(
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        runtime = RuntimeContext(session_state=state)
        return ExecutionContext(identity=identity, runtime=runtime)

    async def execute_turn(
        self,
        session: BrainSession,
        state: SessionState,
        user_prompt: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> TurnResponse:
        """Execute a synchronous single-turn exchange.

        Args:
            session: Target BrainSession.
            state: Active SessionState.
            user_prompt: Incoming user prompt text.
            user_id: Optional user ID.
            workspace_id: Optional workspace ID.

        Returns:
            TurnResponse containing Turn aggregate and TurnMetrics.
        """
        logger.info(f"Executing synchronous turn for session '{session.session_id}'")
        ctx = self.create_context(session, state, user_id=user_id, workspace_id=workspace_id)
        tracer = ExecutionTracer()

        with tracer.span("execute_turn"):
            # 1. Process context through execution pipeline stages
            await self._pipeline.process(ctx)

            # 2. Simulate baseline model turn response
            response_text = f"NexusAI response to: '{user_prompt}'"
            user_message = Message(role=MessageRole.USER, content=user_prompt)
            assistant_message = Message(role=MessageRole.ASSISTANT, content=response_text)

            turn = Turn(
                conversation_id=session.conversation_id,
                user_message=user_message,
                assistant_message=assistant_message,
                token_usage={"input": 20, "output": 15, "total": 35},
                duration_ms=tracer.calculated_latency_ms,
                status="COMPLETED",
            )

            state.turn_count += 1
            tracer.input_tokens = 20
            tracer.output_tokens = 15
            metrics = tracer.finalize_metrics()

            return TurnResponse(
                turn=turn,
                metrics=metrics,
                raw_response_text=response_text,
            )

    async def stream_turn(
        self,
        session: BrainSession,
        state: SessionState,
        user_prompt: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> TurnStream:
        """Execute a streaming single-turn exchange with delta token chunks.

        Args:
            session: Target BrainSession.
            state: Active SessionState.
            user_prompt: Incoming user prompt text.
            user_id: Optional user ID.
            workspace_id: Optional workspace ID.

        Returns:
            A TurnStream async generator wrapper.
        """
        logger.info(f"Streaming turn for session '{session.session_id}'")
        ctx = self.create_context(session, state, user_id=user_id, workspace_id=workspace_id)
        tracer = ExecutionTracer()

        # 1. Process context through execution pipeline stages
        await self._pipeline.process(ctx)

        # 2. Create simulated provider delta chunk stream
        async def mock_chunk_generator() -> AsyncIterator[TurnChunk]:
            yield TurnChunk(delta="NexusAI ", sequence=0)
            yield TurnChunk(delta="streaming ", sequence=1)
            yield TurnChunk(delta=f"response to '{user_prompt}'", sequence=2, finish_reason="stop")

        state.turn_count += 1
        return TurnStream(provider_stream=mock_chunk_generator(), context=ctx, tracer=tracer)
