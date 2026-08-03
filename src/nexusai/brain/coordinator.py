"""
Brain Coordinator: Orchestrates Context Engine, Memory, Tool Execution, and LangGraph Agentic Workflows.
"""

from __future__ import annotations

from typing import Any

from nexusai.brain.prompt import PromptBuilder
from nexusai.brain.workflow.graph import build_agent_graph
from nexusai.brain.workflow.state import NexusGraphState
from nexusai.bus.bus import CommandBus
from nexusai.context.engine import ContextEngine
from nexusai.memory.base import BaseMemory
from nexusai.models.base import BaseModelProvider
from nexusai.tools.registry import ToolRegistry


class BrainCoordinator:
    """Central Orchestrator connecting LLM Provider, Memory, Context, and LangGraph Workflows."""

    def __init__(
        self,
        model_provider: BaseModelProvider,
        registry: ToolRegistry,
        command_bus: CommandBus,
        memory: BaseMemory | None = None,
        context_engine: ContextEngine | None = None,
        prompt_builder: PromptBuilder | None = None,
        security_guard: Any = None,
    ) -> None:
        self.model_provider = model_provider
        self.registry = registry
        self.command_bus = command_bus
        self.memory = memory
        self.context_engine = context_engine
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.security_guard = security_guard

    async def process_user_input(
        self,
        user_text: str,
        session_id: str = "default",
        user_confirmed: bool = False,
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        """Process user input through a LangGraph Agentic Workflow.

        Args:
            user_text: Natural language prompt from the user.
            session_id: Unique session identifier for memory context.
            user_confirmed: Security confirmation flag for high-risk tools.
            max_iterations: Maximum loop iterations safety valve (default: 10).

        Returns:
            Dictionary containing final text output, tool execution status, and iteration count.
        """
        working_context = None
        if self.context_engine:
            working_context = await self.context_engine.gather_context()

        system_prompt = self.prompt_builder.build_system_prompt(context=working_context)

        if self.memory:
            await self.memory.add_message(session_id, "user", user_text)

        if self.memory:
            history = await self.memory.get_messages(session_id)
            messages = [{"role": "system", "content": system_prompt}] + history
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ]

        tools = self.registry.get_all_schemas()

        initial_state: NexusGraphState = {
            "session_id": session_id,
            "messages": messages,
            "tools": tools if tools else None,
            "final_response": None,
            "iterations": 0,
            "user_confirmed": user_confirmed,
            "max_iterations": max_iterations,
            "last_tool_call": None,
        }

        graph = build_agent_graph(self.model_provider, self.command_bus, security_guard=self.security_guard)
        final_state = await graph.ainvoke(initial_state)

        content = final_state.get("final_response") or "Agentic loop reached maximum iterations limit."
        iterations = final_state.get("iterations", 1)

        if self.memory:
            await self.memory.add_message(session_id, "assistant", content)

        return {
            "type": "text",
            "content": content,
            "iterations": iterations,
        }
