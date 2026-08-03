"""
Unit tests for AppleScript engine and macOS desktop automation tools.
"""

import pytest
from unittest.mock import AsyncMock, patch

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.macos.active_window import GetActiveWindowTool
from nexusai.tools.macos.open_app import OpenAppTool
from nexusai.tools.macos.raw_applescript import RawAppleScriptTool
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.system.applescript import execute_applescript


@pytest.mark.asyncio
async def test_execute_applescript_success() -> None:
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Activated\n", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        result = await execute_applescript('tell application "Finder" to activate')
        mock_exec.assert_called_once_with(
            "osascript",
            "-e",
            'tell application "Finder" to activate',
            stdout=-1,
            stderr=-1,
        )
        assert result == "Activated"


@pytest.mark.asyncio
async def test_execute_applescript_failure_raises_tool_execution_error() -> None:
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"Execution error: Application isn't running (-600)")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(ToolExecutionError) as exc_info:
            await execute_applescript('tell application "NonExistentApp" to activate')

        assert "AppleScript execution failed with code 1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_open_app_tool() -> None:
    tool = OpenAppTool()
    assert tool.name == "macos_open_app"
    assert tool.risk_level == RiskLevel.LOW

    with patch("nexusai.tools.macos.open_app.execute_applescript", return_value="") as mock_script:
        result = await tool.execute(app_name="Google Chrome")
        mock_script.assert_called_once_with('tell application "Google Chrome" to activate')
        assert "Google Chrome" in result


@pytest.mark.asyncio
async def test_get_active_window_tool() -> None:
    tool = GetActiveWindowTool()
    assert tool.name == "macos_get_active_window"
    assert tool.risk_level == RiskLevel.LOW

    with patch("nexusai.tools.macos.active_window.execute_applescript", return_value="Terminal::zsh - nexusai") as mock_script:
        result = await tool.execute()
        assert result == {"active_app": "Terminal", "window_title": "zsh - nexusai"}
        assert mock_script.called is True


@pytest.mark.asyncio
async def test_raw_applescript_tool_critical_risk() -> None:
    tool = RawAppleScriptTool()
    assert tool.name == "macos_execute_applescript"
    assert tool.risk_level == RiskLevel.CRITICAL

    with patch("nexusai.tools.macos.raw_applescript.execute_applescript", return_value="Done") as mock_script:
        result = await tool.execute(script='display dialog "NexusAI"')
        mock_script.assert_called_once_with('display dialog "NexusAI"')
        assert result == "Done"


def test_tool_registry_with_macos_tools() -> None:
    registry = ToolRegistry()
    registry.register(OpenAppTool())
    registry.register(GetActiveWindowTool())
    registry.register(RawAppleScriptTool())

    assert registry.has_tool("macos_open_app")
    assert registry.has_tool("macos_get_active_window")
    assert registry.has_tool("macos_execute_applescript")

    schemas = registry.get_all_schemas()
    assert len(schemas) == 3
    schema_names = [s["function"]["name"] for s in schemas]
    assert "macos_open_app" in schema_names
    assert "macos_get_active_window" in schema_names
    assert "macos_execute_applescript" in schema_names
