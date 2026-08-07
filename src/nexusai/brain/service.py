"""BrainRuntimeFacade and AgentRuntimeFacade entry point services for Brain & Agent Runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Any
from uuid import UUID

from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.domain.turn import Message, MessageRole, Turn
from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.pipeline.pipeline import ExecutionPipeline
from nexusai.brain.ports.tool_port import IToolPort
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
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
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.state_machine import AgentState
from nexusai.brain.streaming.stream import TurnStream
from nexusai.brain.telemetry.tracer import ExecutionTracer
from nexusai.logging.logger import logger


@dataclass(frozen=True)
class TurnResponse:
    """Synchronous single-turn response container."""

    turn: Turn
    metrics: TurnMetrics
    raw_response_text: str = ""


@dataclass(frozen=True)
class AgentSessionResponse:
    """Synchronous multi-turn agent session response container.

    Attributes:
        session_id: Target BrainSession UUID.
        goal: Original AgentGoal entity.
        working_memory: Final WorkingMemory snapshot.
        final_state: Final AgentState enum value.
        metrics: Final TurnMetrics diagnostic telemetry.
    """

    session_id: UUID
    goal: AgentGoal
    working_memory: WorkingMemory
    final_state: AgentState
    metrics: TurnMetrics


class BrainRuntimeFacade:
    """Primary public entry point facade for single-turn Brain Runtime orchestration."""

    def __init__(self, pipeline: ExecutionPipeline | None = None) -> None:
        self._pipeline = pipeline or ExecutionPipeline()

    def create_context(
        self,
        session: BrainSession,
        state: SessionState,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ExecutionContext:
        """Construct a unified ExecutionContext transport container for a turn execution."""
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
        """Execute a synchronous single-turn exchange."""
        logger.info(f"Executing synchronous turn for session '{session.session_id}'")
        ctx = self.create_context(session, state, user_id=user_id, workspace_id=workspace_id)
        tracer = ExecutionTracer()

        with tracer.span("execute_turn"):
            await self._pipeline.process(ctx)

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
        """Execute a streaming single-turn exchange with delta token chunks."""
        logger.info(f"Streaming turn for session '{session.session_id}'")
        ctx = self.create_context(session, state, user_id=user_id, workspace_id=workspace_id)
        tracer = ExecutionTracer()

        await self._pipeline.process(ctx)

        async def mock_chunk_generator() -> AsyncIterator[TurnChunk]:
            yield TurnChunk(delta="NexusAI ", sequence=0)
            yield TurnChunk(delta="streaming ", sequence=1)
            yield TurnChunk(delta=f"response to '{user_prompt}'", sequence=2, finish_reason="stop")

        state.turn_count += 1
        return TurnStream(provider_stream=mock_chunk_generator(), context=ctx, tracer=tracer)


class AgentRuntimeFacade:
    """Primary public entry point facade for multi-turn Agent Runtime orchestration."""

    def __init__(
        self,
        loop_executor: LoopExecutor | None = None,
        tool_port: IToolPort | None = None,
    ) -> None:
        self._executor = loop_executor or LoopExecutor(tool_port=tool_port)
        self._brain_facade = BrainRuntimeFacade()

    def create_agent_context(
        self,
        session: BrainSession,
        goal: AgentGoal,
        state: SessionState,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> AgentRuntimeContext:
        """Construct an AgentRuntimeContext container for multi-turn agent execution."""
        exec_ctx = self._brain_facade.create_context(
            session=session, state=state, user_id=user_id, workspace_id=workspace_id
        )
        working_mem = WorkingMemory(goal=goal)
        return AgentRuntimeContext(execution_context=exec_ctx, working_memory=working_mem)

    async def run_agent_session(
        self,
        session: BrainSession,
        goal: AgentGoal,
        state: SessionState,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> AgentSessionResponse:
        """Execute a multi-turn autonomous agent session for a given goal.

        Args:
            session: Target BrainSession.
            goal: AgentGoal task description.
            state: Active SessionState.
            user_id: Optional user ID.
            workspace_id: Optional workspace ID.

        Returns:
            AgentSessionResponse summary.
        """
        logger.info(f"[AgentRuntimeFacade] Starting multi-turn session for goal '{goal.description}'")
        agent_ctx = self.create_agent_context(
            session=session, goal=goal, state=state, user_id=user_id, workspace_id=workspace_id
        )
        tracer = ExecutionTracer()

        with tracer.span("run_agent_session"):
            final_mem = await self._executor.execute_loop(agent_ctx)
            final_state = agent_ctx.state_machine.current_state

            tracer.input_tokens = len(final_mem.observations) * 15
            tracer.output_tokens = len(final_mem.steps) * 20
            metrics = tracer.finalize_metrics()

            return AgentSessionResponse(
                session_id=session.session_id,
                goal=goal,
                working_memory=final_mem,
                final_state=final_state,
                metrics=metrics,
            )
