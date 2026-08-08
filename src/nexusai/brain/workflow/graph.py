"""
LangGraph StateGraph builder for Agentic Workflow Orchestration.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from nexusai.brain.workflow.nodes import node_reasoner, node_tool_executor
from nexusai.brain.workflow.state import NexusGraphState
from nexusai.bus.bus import CommandBus
from nexusai.models.base import BaseModelProvider


def should_continue(state: NexusGraphState) -> str:
    """Evaluate conditional edges based on completion status or iteration limits."""
    if state.get("final_response") is not None:
        return END
    if state.get("iterations", 0) >= state.get("max_iterations", 10):
        return END
    return "tool_executor"


def build_agent_graph(
    model_provider: BaseModelProvider,
    command_bus: CommandBus,
    security_guard: Any = None,
) -> Any:
    """Build and compile the LangGraph workflow graph."""
    workflow = StateGraph(NexusGraphState)

    async def reasoner_node(state: NexusGraphState) -> dict[str, Any]:
        return await node_reasoner(state, model_provider)

    async def tool_executor_node(state: NexusGraphState) -> dict[str, Any]:
        return await node_tool_executor(state, command_bus, security_guard=security_guard)

    workflow.add_node("reasoner", reasoner_node)
    workflow.add_node("tool_executor", tool_executor_node)

    workflow.set_entry_point("reasoner")

    workflow.add_conditional_edges(
        "reasoner",
        should_continue,
        {
            "tool_executor": "tool_executor",
            END: END,
        },
    )

    workflow.add_edge("tool_executor", "reasoner")

    return workflow.compile()
