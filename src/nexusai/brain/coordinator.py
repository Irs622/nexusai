"""BrainCoordinator module orchestration facade for CLI and Web API Server integration."""

from __future__ import annotations

import json
import time
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

        effective_session_id = session_id or "cli_session"

        # 1. Retrieve conversation history from memory if available
        history: list[dict[str, Any]] = []
        if self.memory and hasattr(self.memory, "get_messages"):
            try:
                history = await self.memory.get_messages(effective_session_id, limit=20)
            except Exception:
                pass

        messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        for h in history:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})

        # 2. Resolve tool availability & schemas
        tools_schema: list[dict[str, Any]] = []
        available_tools: list[str] = []

        if self.registry:
            if hasattr(self.registry, "get_all_schemas"):
                tools_schema = self.registry.get_all_schemas()
            elif hasattr(self.registry, "get_tools_schema"):
                tools_schema = self.registry.get_tools_schema()
            elif hasattr(self.registry, "get_schemas"):
                tools_schema = self.registry.get_schemas()

            if hasattr(self.registry, "list_tools"):
                available_tools = list(self.registry.list_tools())
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

        # 3. Construct PlanningContext & execute DAG PlanGraph via PlanGraphExecutionEngine
        goal = AgentGoal(description=user_text)
        planning_ctx = PlanningContext(
            goal_component=PlanningGoal(goal=goal),
            resources_component=PlanningResources(available_tools=tuple(available_tools)),
        )

        plan_graph, exec_results, decision_trace = await self.execution_engine.execute_plan(
            planning_ctx, tool_port=tool_port, session_id=effective_session_id
        )

        self.last_plan_graph = plan_graph
        self.last_execution_results = exec_results
        self.last_decision_trace = decision_trace

        # 4. Synchronize BrainRuntimeFacade context
        session = BrainSession()
        state = SessionState()
        self.facade.create_context(session=session, state=state)

        # 5. Synthesize LLM Response via ModelProvider if present
        if self.model_provider:
            if hasattr(self.model_provider, "last_messages"):
                self.model_provider.last_messages = messages
            if hasattr(self.model_provider, "last_tools"):
                self.model_provider.last_tools = tools_schema

            if hasattr(self.model_provider, "chat"):
                res = await self.model_provider.chat(messages, tools=tools_schema if tools_schema else None)
                if isinstance(res, dict) and res.get("type") == "tool_call":
                    tool_name = str(res.get("tool_name", ""))
                    arguments = res.get("arguments", {})
                    if not isinstance(arguments, dict):
                        arguments = {}

                    tool_result: Any = None
                    exec_error: str | None = None
                    if self.command_bus and hasattr(self.command_bus, "dispatch"):
                        try:
                            from nexusai.bus.commands import ExecuteToolCommand

                            cmd = ExecuteToolCommand(tool_name=tool_name, arguments=arguments, user_confirmed=True)
                            tool_result = await self.command_bus.dispatch(cmd)
                        except Exception as err:
                            exec_error = str(err)
                    elif self.registry and hasattr(self.registry, "get"):
                        try:
                            tool_inst = self.registry.get(tool_name)
                            tool_result = await tool_inst.execute(**arguments)
                        except Exception as err:
                            exec_error = str(err)

                    result_content = str(tool_result) if exec_error is None else f"Error executing {tool_name}: {exec_error}"
                    call_id = f"call_{tool_name}_{int(time.time() * 1000)}"

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                        }],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": result_content,
                    })

                    # Follow up to get final answer from model
                    final_res = await self.model_provider.chat(messages)
                    if isinstance(final_res, dict):
                        res_copy = dict(final_res)
                        final_content = res_copy.get("content", "")
                    else:
                        final_content = str(final_res)
                        res_copy = {"type": "text", "content": final_content}

                    if self.memory and hasattr(self.memory, "add_message"):
                        try:
                            await self.memory.add_message(effective_session_id, "user", user_text)
                            await self.memory.add_message(effective_session_id, "assistant", final_content)
                        except Exception:
                            pass

                    res_copy["trace_id"] = decision_trace.trace_id
                    res_copy["plan_nodes"] = len(plan_graph.nodes)
                    return res_copy

                elif isinstance(res, dict):
                    res_copy = dict(res)
                    content = res_copy.get("content", "")
                    if self.memory and hasattr(self.memory, "add_message"):
                        try:
                            await self.memory.add_message(effective_session_id, "user", user_text)
                            await self.memory.add_message(effective_session_id, "assistant", content)
                        except Exception:
                            pass
                    if "iterations" not in res_copy:
                        res_copy["iterations"] = 1
                    res_copy["trace_id"] = decision_trace.trace_id
                    res_copy["plan_nodes"] = len(plan_graph.nodes)
                    return res_copy

        # 6. Offline / Mock response fallback when no model_provider is active
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
