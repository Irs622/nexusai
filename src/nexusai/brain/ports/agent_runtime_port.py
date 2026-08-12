"""IAgentRuntime protocol contract for high-level Agent orchestration."""

from __future__ import annotations

from typing import Protocol

from nexusai.brain.domain.agent_runtime import AgentRequest, AgentResponse
from nexusai.brain.ports.tool_port import IToolPort


class IAgentRuntime(Protocol):
    """Abstract facade interface isolating consumers from internal Agent runtime mechanics."""

    async def run_agent(
        self,
        request: AgentRequest,
        tool_port: IToolPort,
    ) -> AgentResponse:
        """Orchestrate natural language AgentRequest through context assembly, planning, governance, and execution."""
        ...

    async def resume_agent(
        self,
        execution_id: str,
        request: AgentRequest,
        tool_port: IToolPort,
    ) -> AgentResponse:
        """Resume an interrupted Agent execution enforcing session identity and plan identity validation."""
        ...

    async def cancel_agent(self, execution_id: str) -> bool:
        """Cancel an active Agent execution task."""
        ...
