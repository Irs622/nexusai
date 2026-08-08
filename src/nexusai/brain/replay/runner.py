"""ReplayRecorder and ReplayRunner for deterministic agent loop execution replay."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.replay.serialization import ExecutionEvent, ExecutionLog
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.runtime.working_memory import WorkingMemory


class ReplayRecorder:
    """Records turn execution events during live agent loop execution."""

    def __init__(self, session_id: str, goal_description: str) -> None:
        self.session_id = session_id
        self.goal_description = goal_description
        self._events: list[ExecutionEvent] = []

    def record_turn(
        self,
        turn_index: int,
        step_title: str,
        tool_name: str,
        tool_arguments: dict[str, str],
        observation_payload: str,
        observation_success: bool,
        compaction_triggered: bool,
        summary_text: str,
        decision: str,
    ) -> ExecutionEvent:
        """Record a single turn execution event."""
        event = ExecutionEvent(
            event_id=str(uuid4()),
            session_id=self.session_id,
            turn_index=turn_index,
            step_title=step_title,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            observation_payload=observation_payload,
            observation_success=observation_success,
            compaction_triggered=compaction_triggered,
            summary_text=summary_text,
            decision=decision,
            timestamp=time.time(),
        )
        self._events.append(event)
        return event

    def build_log(self) -> ExecutionLog:
        """Build immutable ExecutionLog container."""
        return ExecutionLog(
            session_id=self.session_id,
            goal_description=self.goal_description,
            events=tuple(self._events),
        )


class ReplayToolPort(IToolPort):
    """ToolPort adapter replaying observation payloads from a recorded ExecutionLog."""

    def __init__(self, log: ExecutionLog) -> None:
        self.log = log
        self._event_index = 0

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Return pre-recorded tool execution result for current step."""
        if self._event_index < len(self.log.events):
            event = self.log.events[self._event_index]
            self._event_index += 1
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=event.observation_success,
                result=event.observation_payload if event.observation_success else None,
                error_message=event.observation_payload if not event.observation_success else None,
            )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            success=True,
            result="Replay completed payload.",
        )


class ReplayRunner:
    """Replays a recorded ExecutionLog through LoopExecutor to produce deterministic state snapshots."""

    def __init__(self, deps: RuntimeDependencies | None = None) -> None:
        self.deps = deps or RuntimeDependencies()

    async def replay(self, log: ExecutionLog) -> WorkingMemory:
        """Replay execution log deterministically through LoopExecutor."""
        replay_tool_port = ReplayToolPort(log)
        executor = LoopExecutor(deps=self.deps, tool_port=replay_tool_port)

        facade = AgentRuntimeBuilder().build()
        facade._executor = executor

        session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
        goal = AgentGoal(description=log.goal_description)
        state = SessionState(provider_id="replay-provider", active_model="replay-model-v1")

        agent_ctx = facade.create_agent_context(session=session, goal=goal, state=state)

        # Execute loop deterministically using recorded events
        final_memory = await executor.execute_loop(agent_ctx)
        return final_memory

    async def replay_file(self, jsonl_file_path: Path | str) -> WorkingMemory:
        """Load JSONL file and replay deterministically."""
        log = ExecutionLog.load_jsonl(jsonl_file_path)
        return await self.replay(log)
