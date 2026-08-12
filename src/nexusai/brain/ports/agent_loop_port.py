"""IAgentLoop protocol contract interface for Planning -> Execution -> Observation Loop control."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.agent_loop import AgentLoopConfig, AgentLoopResult
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.ports.tool_port import IToolPort


class IAgentLoop(Protocol):
    """Abstract port interface for executing governed Planning -> Execution -> Observation control loops."""

    async def run(
        self,
        request: AgentRequest,
        config: AgentLoopConfig,
        tool_port: IToolPort,
    ) -> AgentLoopResult:
        """Run the Planning -> Execution -> Observation loop under explicit iteration ceilings and state machine bounds."""
        ...

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an active agent loop execution task."""
        ...
