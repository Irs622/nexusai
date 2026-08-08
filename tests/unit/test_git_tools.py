"""
Unit tests for Git Status Tool.
"""

from unittest.mock import AsyncMock, patch

import pytest

from nexusai.security.guard import RiskLevel
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.git import GitStatusTool


@pytest.mark.asyncio
async def test_git_status_tool_success() -> None:
    tool = GitStatusTool()
    assert tool.name == "workspace_git_status"
    assert tool.risk_level == RiskLevel.LOW

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"On branch main\nnothing to commit", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        result = await tool.execute()
        mock_shell.assert_called_once_with(
            "git status",
            stdout=-1,
            stderr=-1,
        )
        assert "On branch main" in result


@pytest.mark.asyncio
async def test_git_status_tool_error() -> None:
    tool = GitStatusTool()

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"fatal: not a git repository")
    mock_process.returncode = 128

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            result = await tool.execute()
            assert "Git error" in result
            assert "not a git repository" in result


def test_git_status_tool_registry() -> None:
    registry = ToolRegistry()
    registry.register(GitStatusTool())
    assert registry.has_tool("workspace_git_status")
