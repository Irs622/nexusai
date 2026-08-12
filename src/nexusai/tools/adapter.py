"""ToolRegistryAdapter implementing IToolPort to bridge ToolRegistry with Brain Runtime."""

from __future__ import annotations

import asyncio
import inspect
import time

from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.core.errors import ToolExecutionError
from nexusai.logging.logger import logger
from nexusai.tools.registry import ToolRegistry


class ToolRegistryAdapter(IToolPort):
    """Adapter class wrapping ToolRegistry to implement IToolPort contract with isolated thread execution for synchronous tools."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or ToolRegistry()

    @property
    def registry(self) -> ToolRegistry:
        """Get wrapped ToolRegistry instance."""
        return self._registry

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute tool request against registered ToolRegistry instances.

        Catches tool errors and timeouts cleanly and returns structured ToolExecutionResult.
        Executes synchronous tools in worker threads via asyncio.to_thread to prevent event-loop blocking.

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
                request_id=request.execution_id,
            )

        timeout_sec = request.timeout_seconds if request.timeout_seconds is not None else 30.0

        try:
            tool_instance = self._registry.get(request.tool_name)
            exec_args = dict(request.arguments)

            if hasattr(tool_instance, "execute") and callable(tool_instance.execute):
                sig = inspect.signature(tool_instance.execute)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if "timeout_seconds" in sig.parameters or has_kwargs:
                    if "timeout_seconds" not in exec_args:
                        exec_args["timeout_seconds"] = timeout_sec

                if inspect.iscoroutinefunction(tool_instance.execute):
                    if timeout_sec and timeout_sec > 0:
                        output = await asyncio.wait_for(
                            tool_instance.execute(**exec_args),
                            timeout=timeout_sec,
                        )
                    else:
                        output = await tool_instance.execute(**exec_args)
                else:
                    # Synchronous tool: execute in worker thread to isolate event loop
                    if timeout_sec and timeout_sec > 0:
                        output = await asyncio.wait_for(
                            asyncio.to_thread(tool_instance.execute, **exec_args),
                            timeout=timeout_sec,
                        )
                    else:
                        output = await asyncio.to_thread(tool_instance.execute, **exec_args)
            elif callable(tool_instance):
                if inspect.iscoroutinefunction(tool_instance):
                    if timeout_sec and timeout_sec > 0:
                        output = await asyncio.wait_for(
                            tool_instance(**exec_args),
                            timeout=timeout_sec,
                        )
                    else:
                        output = await tool_instance(**exec_args)
                else:
                    # Synchronous callable tool: execute in worker thread
                    if timeout_sec and timeout_sec > 0:
                        output = await asyncio.wait_for(
                            asyncio.to_thread(tool_instance, **exec_args),
                            timeout=timeout_sec,
                        )
                    else:
                        output = await asyncio.to_thread(tool_instance, **exec_args)
            else:
                raise ToolExecutionError(f"Tool instance '{request.tool_name}' is not callable.")

            elapsed = (time.perf_counter() - start_time) * 1000.0
            logger.debug(
                f"[ToolRegistryAdapter] Tool '{request.tool_name}' completed in {elapsed:.2f}ms"
            )
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=True,
                output=output,
                error_message=None,
                execution_time_ms=elapsed,
                request_id=request.execution_id,
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Tool execution timed out after {timeout_sec:.2f} seconds for '{request.tool_name}'"
            logger.error(f"[ToolRegistryAdapter] {err_msg}")
            return ToolExecutionResult(
                tool_name=request.tool_name,
                success=False,
                output=None,
                error_message=err_msg,
                execution_time_ms=elapsed,
                request_id=request.execution_id,
            )
        except asyncio.CancelledError:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            logger.warning(f"[ToolRegistryAdapter] Tool execution cancelled for '{request.tool_name}'")
            raise
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
                request_id=request.execution_id,
            )
