"""Unit and integration tests for Milestone Alpha AI OS end-to-end product features."""

import pytest

from nexusai.brain.planner import TaskPlanner
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.selector import ToolSelector
from nexusai.tools.system.terminal import TerminalTool
from nexusai.tools.workspace.fs import ListDirectoryTool, ReadFileTool
from plugins.git.plugin import GitPlugin


def test_task_planner_decomposes_prompt() -> None:
    planner = TaskPlanner()
    plan = planner.plan("Buat aplikasi Todo menggunakan Next.js")
    assert plan.prompt == "Buat aplikasi Todo menggunakan Next.js"
    assert len(plan.steps) >= 3
    assert plan.steps[0].tool_name == "workspace_list_directory"


def test_tool_selector_ranks_best_tool() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(ListDirectoryTool())
    registry.register(TerminalTool())

    selector = ToolSelector(registry)
    selected = selector.select_best_tool("Read file contents from pyproject.toml")
    assert selected.name == "workspace_read_file"


@pytest.mark.asyncio
async def test_git_plugin_execution() -> None:
    plugin = GitPlugin()
    tools = plugin.get_tools()
    assert len(tools) == 1

    git_tool = tools[0]
    result = await git_tool.execute()
    assert isinstance(result, str)
