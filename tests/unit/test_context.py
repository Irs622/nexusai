"""
Unit tests for Context Engine and Working Context.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexusai.context.engine import ContextEngine, WorkingContext


@pytest.mark.asyncio
async def test_context_engine_gather_context_success() -> None:
    mock_window_tool = AsyncMock()
    mock_window_tool.execute.return_value = {
        "active_app": "VS Code",
        "window_title": "main.py - NexusAI",
    }

    mock_git_process = AsyncMock()
    mock_git_process.communicate.return_value = (b"feature/context-engine\n", b"")
    mock_git_process.returncode = 0

    mock_mem = MagicMock()
    mock_mem.percent = 42.5

    with patch("nexusai.context.engine.GetActiveWindowTool", return_value=mock_window_tool):
        with patch("asyncio.create_subprocess_shell", return_value=mock_git_process):
            with patch("psutil.cpu_percent", return_value=12.4):
                with patch("psutil.virtual_memory", return_value=mock_mem):
                    engine = ContextEngine()
                    context = await engine.gather_context()

                    assert isinstance(context, WorkingContext)
                    assert context.active_application == "VS Code"
                    assert context.active_window_title == "main.py - NexusAI"
                    assert context.git_branch == "feature/context-engine"
                    assert context.cpu_usage_percent == 12.4
                    assert context.memory_usage_percent == 42.5


@pytest.mark.asyncio
async def test_context_engine_fallback_on_exceptions() -> None:
    mock_window_tool = AsyncMock()
    mock_window_tool.execute.side_effect = Exception("OS Permission Error")

    with patch("nexusai.context.engine.GetActiveWindowTool", return_value=mock_window_tool):
        with patch("asyncio.create_subprocess_shell", side_effect=Exception("Git not installed")):
            with patch("psutil.cpu_percent", side_effect=Exception("psutil error")):
                engine = ContextEngine()
                context = await engine.gather_context()

                assert context.active_application == "Unknown"
                assert context.active_window_title == "Unknown"
                assert context.git_branch is None
                assert context.cpu_usage_percent == 0.0
                assert context.memory_usage_percent == 0.0
