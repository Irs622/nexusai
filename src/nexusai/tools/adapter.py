"""ToolRegistryAdapter implementing IToolPort to bridge ToolRegistry with Brain Runtime."""

from __future__ import annotations

import time
import inspect
from typing import Any
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.registry import ToolRegistry


class ToolRegistryAdapter(IToolPort):
    """Adapter class wrapping ToolRegistry to implement IToolPort contract for Brain Runtime."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or ToolRegistry()

    @property
    def registry(self) -> ToolRegistry:
        """Get wrapped ToolRegistry instance."""
        return self._registry

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute tool request against registered ToolRegistry instances.

        Catches tool errors cleanly and returns structured ToolExecutionResult.

        Args:
            request: ToolExecutionRequest container.

        Returns:
            ToolExecutionResult entity.
        """
        start_time = time.perf_counter()
        logger.debug(f"[ToolRegistryAdapter] Executing tool request for '{request.tool_name}'")

        if not self._registry.has_tool(request.tool_name):
            err_msg = f"Tool '{request.tool_name}' is not registered in ToolRegistry"
            logger.warning(f"[ToolRegistryAdapter] {err_msg}")
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=False,
                output=None,
                error_message=err_msg,
                execution_time_ms=elapsed,
            )

        try:
            tool_instance = self._registry.get(request.tool_name)
            # Execute tool instance (supporting async and sync tools)
            if hasattr(tool_instance, "execute"):
                if inspect.iscoroutinefunction(tool_instance.execute):
                    output = await tool_instance.execute(**request.arguments)
                else:
                    output = tool_instance.execute(**request.arguments)
            elif callable(tool_instance):
                if inspect.iscoroutinefunction(tool_instance):
                    output = await tool_instance(**request.arguments)
                else:
                    output = tool_instance(**request.arguments)
            else:
                raise ToolExecutionError(f"Tool instance '{request.tool_name}' is not callable.")

            elapsed = (time.perf_counter() - start_time) * 1000.0
            logger.debug(f"[ToolRegistryAdapter] Tool '{request.tool_name}' completed in {elapsed:.2f}ms")
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=True,
                output=output,
                error_message=None,
                execution_time_ms=elapsed,
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Tool execution failed for '{request.tool_name}': {str(exc)}"
            logger.error(f"[ToolRegistryAdapter] {err_msg}")
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=False,
                output=None,
                error_message=err_msg,
                execution_time_ms=elapsed,
            )
