"""End-to-end integration test driving CLI/Brain -> Bus -> Memory -> Tool pipeline."""
import pathlib
import pytest
from nexusai.core.config import SecuritySettings
from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ReadFileTool
from nexusai.security.guard import SecurityGuard
from nexusai.memory.sqlite_memory import SQLiteMemory

@pytest.mark.asyncio
async def test_full_pipeline_tool_execution(tmp_path: pathlib.Path) -> None:
    """E2E pipeline test executing a tool command through CQRS bus and memory."""
    db_path = str(tmp_path / "test_memory.db")
    memory = SQLiteMemory(db_path=db_path)
    await memory.initialize_db()
    
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    
    settings = SecuritySettings(strict_mode=False, auto_approve_low_risk=True)
    security_guard = SecurityGuard(settings)
    event_bus = EventBus()
    command_bus = CommandBus()
    
    handler = ExecuteToolCommandHandler(registry, security_guard, event_bus)
    command_bus.register(ExecuteToolCommand, handler)
    
    command = ExecuteToolCommand(tool_name="workspace_read_file", arguments={"file_path": "pyproject.toml"})
    result = await command_bus.dispatch(command)
    
    assert isinstance(result, str)
    assert "nexusai" in result.lower() or "version" in result.lower()
    
    await memory.add_message("test_session", "user", "Read pyproject.toml")
    history = await memory.get_messages("test_session")
    assert len(history) == 1
    assert history[0]["content"] == "Read pyproject.toml"
