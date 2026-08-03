"""Integration tests for failure path recovery and security blocks."""
import pathlib
import pytest
from nexusai.core.config import SecuritySettings
from nexusai.core.errors import CommandExecutionError, NexusAIError
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ReadFileTool
from nexusai.security.guard import SecurityGuard

@pytest.mark.asyncio
async def test_failure_path_nonexistent_file_returns_error_string() -> None:
    """Failure Path: Reading non-existent file returns user-friendly error string."""
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    
    settings = SecuritySettings(strict_mode=False, auto_approve_low_risk=True)
    security_guard = SecurityGuard(settings)
    event_bus = EventBus()
    command_bus = CommandBus()
    
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    command_bus.register(ExecuteToolCommand, handler)
    
    command = ExecuteToolCommand(tool_name="workspace_read_file", arguments={"file_path": "non_existent_file_xyz.txt"})
    result = await command_bus.dispatch(command)
    assert "Error: File 'non_existent_file_xyz.txt' not found." in result

@pytest.mark.asyncio
async def test_failure_path_unregistered_tool_raises_exception() -> None:
    """Failure Path: Invoking unregistered tool raises CommandExecutionError."""
    registry = ToolRegistry()
    settings = SecuritySettings()
    security_guard = SecurityGuard(settings)
    event_bus = EventBus()
    command_bus = CommandBus()
    
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    command_bus.register(ExecuteToolCommand, handler)
    
    command = ExecuteToolCommand(tool_name="unregistered_tool", arguments={})
    with pytest.raises((CommandExecutionError, NexusAIError)):
        await command_bus.dispatch(command)
