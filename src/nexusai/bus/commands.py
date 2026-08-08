"""
CQRS Commands & Command Handlers for NexusAI.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from nexusai.bus.bus import EventBus
from nexusai.bus.events import ToolExecutedEvent
from nexusai.core.errors import SecurityError, ToolExecutionError
from nexusai.security.guard import ActionRequest, SecurityGuard
from nexusai.tools.registry import ToolRegistry


class ExecuteToolCommand(BaseModel):
    """Command payload to trigger tool execution through the CQRS command bus."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    user_confirmed: bool = False


class ExecuteToolCommandHandler:
    """Handler executing tool calls with schema validation and security checks."""

    def __init__(
        self,
        registry: ToolRegistry,
        security_guard: SecurityGuard,
        event_bus: EventBus,
    ) -> None:
        self.registry = registry
        self.security_guard = security_guard
        self.event_bus = event_bus

    async def __call__(self, command: ExecuteToolCommand) -> Any:
        """Process the ExecuteToolCommand."""
        tool = self.registry.get(command.tool_name)

        # 1. Validate arguments against Pydantic schema
        try:
            validated_args = tool.input_schema(**command.arguments)
        except ValidationError as ve:
            raise ToolExecutionError(
                f"Invalid arguments for tool '{tool.name}': {ve}",
                details={"errors": str(ve.errors())},
            ) from ve

        # 2. Convert arguments to string dict for security guard evaluation
        string_params = {k: str(v) for k, v in command.arguments.items()}
        action_request = ActionRequest(
            action_name=f"tool:{tool.name}",
            risk_level=tool.risk_level,
            description=tool.description,
            parameters=string_params,
        )

        # 3. Evaluate Security Guard authorization
        is_permitted = self.security_guard.evaluate_permission(
            action_request,
            user_confirmed=command.user_confirmed,
        )

        if not is_permitted:
            raise SecurityError(
                f"Security policy denied execution of tool '{tool.name}' (Risk Level: {tool.risk_level.value}). User confirmation required.",
                details={"tool_name": tool.name, "risk_level": tool.risk_level.value},
            )

        # 4. Execute tool logic safely
        try:
            result = await tool.execute(**validated_args.model_dump())
            await self.event_bus.publish(
                ToolExecutedEvent(
                    tool_name=tool.name,
                    arguments=command.arguments,
                    result=result,
                    success=True,
                )
            )
            return result
        except Exception as e:
            await self.event_bus.publish(
                ToolExecutedEvent(
                    tool_name=tool.name,
                    arguments=command.arguments,
                    result=None,
                    success=False,
                    error=str(e),
                )
            )
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError(f"Tool '{tool.name}' execution failed: {e}") from e
