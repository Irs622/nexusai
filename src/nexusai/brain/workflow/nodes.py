"""
LangGraph Nodes for LLM Reasoning and Tool Execution.
"""

from __future__ import annotations

from typing import Any

from nexusai.brain.workflow.state import NexusGraphState
from nexusai.bus.bus import CommandBus
from nexusai.bus.commands import ExecuteToolCommand
from nexusai.core.errors import SecurityError
from nexusai.models.base import BaseModelProvider
from nexusai.security.guard import ActionRequest, RiskLevel, SecurityGuard


async def node_reasoner(
    state: NexusGraphState,
    model_provider: BaseModelProvider,
) -> dict[str, Any]:
    """Graph node querying LLM model provider for reasoning and tool invocation intents."""
    messages = list(state.get("messages", []))
    tools = state.get("tools")

    llm_response = await model_provider.chat(messages, tools=tools if tools else None)
    curr_iterations = state.get("iterations", 0) + 1

    if llm_response.get("type") == "tool_call":
        tool_call_dict = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": llm_response.get("id", llm_response["tool_name"]),
                    "type": "function",
                    "function": {
                        "name": llm_response["tool_name"],
                        "arguments": str(llm_response.get("arguments", {})),
                    },
                }
            ],
        }
        messages.append(tool_call_dict)
        return {
            "messages": messages,
            "last_tool_call": llm_response,
            "iterations": curr_iterations,
        }

    return {
        "final_response": llm_response.get("content", ""),
        "iterations": curr_iterations,
    }


async def node_tool_executor(
    state: NexusGraphState,
    command_bus: CommandBus,
    security_guard: SecurityGuard | None = None,
) -> dict[str, Any]:
    """Graph node executing tool calls via CommandBus and appending outputs to messages."""
    last_call = state.get("last_tool_call")
    if not last_call:
        return {"last_tool_call": None}

    tool_name = last_call["tool_name"]
    arguments = last_call.get("arguments", {})
    user_confirmed = state.get("user_confirmed", False)

    if security_guard:
        action_request = ActionRequest(
            action_name=tool_name,
            risk_level=last_call.get("risk_level", RiskLevel.HIGH),
            description=f"Execute tool '{tool_name}'",
            parameters={k: str(v) for k, v in arguments.items()},
        )
        if not security_guard.evaluate_permission(action_request, user_confirmed=user_confirmed):
            raise SecurityError(
                f"Action '{tool_name}' denied by SecurityGuard policy",
                details={"tool_name": tool_name, "arguments": arguments},
            )

    cmd = ExecuteToolCommand(
        tool_name=tool_name,
        arguments=arguments,
        user_confirmed=user_confirmed,
    )
    result = await command_bus.dispatch(cmd)

    current_messages = list(state.get("messages", []))
    current_messages.append({
        "role": "tool",
        "tool_call_id": last_call.get("id", tool_name),
        "content": str(result),
        "name": tool_name,
    })

    return {
        "messages": current_messages,
        "last_tool_call": None,
    }

