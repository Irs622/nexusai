"""BrainCoordinator module orchestration facade for CLI and Web API Server integration."""

from __future__ import annotations

from typing import Any, Dict

from nexusai.brain.domain.agent import AgentGoal, PlanningContext, PlanningGoal, PlanningResources
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.tool_port import IToolPort
from nexusai.brain.prompt import PromptBuilder
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.runtime.state import SessionState
from nexusai.brain.service import BrainRuntimeFacade
from nexusai.tools.adapter import ToolRegistryAdapter


class BrainCoordinator:
    """Coordinator orchestration facade connecting Providers, Tools, Bus, Memory, and Brain Runtime."""

    def __init__(
        self,
        model_provider: Any = None,
        registry: Any = None,
        command_bus: Any = None,
        memory: Any = None,
        context_engine: Any = None,
        execution_engine: PlanGraphExecutionEngine | None = None,
        facade: BrainRuntimeFacade | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.model_provider = model_provider
        self.registry = registry
        self.command_bus = command_bus
        self.memory = memory
        self.context_engine = context_engine
        self.facade = facade or BrainRuntimeFacade()
        self.execution_engine = execution_engine or PlanGraphExecutionEngine()
        self.last_decision_trace: Any = None
        self.last_plan_graph: Any = None
        self.last_execution_results: Any = None

    async def process_user_input(
        self,
        user_text: str,
        session_id: str = "",
        user_confirmed: bool = True,
    ) -> Dict[str, Any]:
        """Process user text input through Brain Runtime DAG pipeline (Planner -> Validator -> Engine -> Provider)."""
        sys_prompt = PromptBuilder().DEFAULT_SYSTEM_PROMPT
        if self.context_engine:
            try:
                working_ctx = await self.context_engine.gather_context()
                sys_prompt = PromptBuilder().build_system_prompt(context=working_ctx)
            except Exception:
                pass

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text},
        ]

        # 1. Resolve tool availability & IToolPort bridge
        tools_schema: list[dict[str, Any]] = []
        available_tools: list[str] = []

        if self.registry:
            if hasattr(self.registry, "get_tools_schema"):
                tools_schema = self.registry.get_tools_schema()
            if hasattr(self.registry, "list_tools"):
                available_tools = list(self.registry.list_tools())
            elif hasattr(self.registry, "get_all_schemas"):
                available_tools = [
                    s["function"]["name"] for s in self.registry.get_all_schemas() if "function" in s and "name" in s["function"]
                ]
            elif tools_schema:
                available_tools = [
                    t["function"]["name"] for t in tools_schema if "function" in t and "name" in t["function"]
                ]

        tool_port: IToolPort
        if hasattr(self.registry, "has_tool") and hasattr(self.registry, "get"):
            tool_port = ToolRegistryAdapter(self.registry)
        elif isinstance(self.registry, IToolPort):
            tool_port = self.registry
        else:
            tool_port = ToolRegistryAdapter()

        # 2. Construct PlanningContext & execute DAG PlanGraph via PlanGraphExecutionEngine
        goal = AgentGoal(description=user_text)
        planning_ctx = PlanningContext(
            goal_component=PlanningGoal(goal=goal),
            resources_component=PlanningResources(available_tools=tuple(available_tools)),
        )

        effective_session_id = session_id or "session-1"
        plan_graph, exec_results, decision_trace = await self.execution_engine.execute_plan(
            planning_ctx, tool_port=tool_port, session_id=effective_session_id
        )

        self.last_plan_graph = plan_graph
        self.last_execution_results = exec_results
        self.last_decision_trace = decision_trace

        # 3. Synchronize BrainRuntimeFacade context
        session = BrainSession(session_id=effective_session_id)
        state = SessionState()
        self.facade.create_context(session=session, state=state)

        # 4. Synthesize LLM Response via ModelProvider if present
        if self.model_provider:
            if hasattr(self.model_provider, "last_messages"):
                self.model_provider.last_messages = messages
            if hasattr(self.model_provider, "last_tools"):
                self.model_provider.last_tools = tools_schema

            if hasattr(self.model_provider, "chat"):
                res = await self.model_provider.chat(messages, tools=tools_schema)
                if isinstance(res, dict):
                    res_copy = dict(res)
                    if "iterations" not in res_copy:
                        res_copy["iterations"] = 1
                    res_copy["trace_id"] = decision_trace.trace_id
                    res_copy["plan_nodes"] = len(plan_graph.nodes)
                    return res_copy

        # 5. Offline / Mock response fallback when no model_provider is active
        return {
            "type": "text",
            "content": f"Processed: {user_text}",
            "session_id": effective_session_id,
            "status": "COMPLETED",
            "iterations": 1,
            "trace_id": decision_trace.trace_id,
            "plan_nodes": len(plan_graph.nodes),
            "executed_results": len(exec_results),
        }


__all__ = ["BrainCoordinator"]
