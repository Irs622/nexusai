"""
Unit tests for Workspace File System Tools.
"""

import pytest
from pathlib import Path

from nexusai.security.guard import RiskLevel
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ListDirectoryTool, ReadFileTool


@pytest.mark.asyncio
async def test_list_directory_tool(tmp_path: Path) -> None:
    # Create sample files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.py").write_text("print('hello')")
    (tmp_path / "subdir").mkdir()

    tool = ListDirectoryTool()
    assert tool.name == "workspace_list_directory"
    assert tool.risk_level == RiskLevel.LOW

    result = await tool.execute(path=str(tmp_path))
    assert isinstance(result, list)
    assert result == ["file1.txt", "file2.py", "subdir"]


@pytest.mark.asyncio
async def test_list_directory_non_existent_path() -> None:
    tool = ListDirectoryTool()
    result = await tool.execute(path="/non_existent_path_12345")
    assert "Error:" in str(result)


@pytest.mark.asyncio
async def test_read_file_tool(tmp_path: Path) -> None:
    sample_file = tmp_path / "config.yaml"
    sample_file.write_text("app_name: NexusAI\nversion: 0.1.0")

    tool = ReadFileTool()
    assert tool.name == "workspace_read_file"
    assert tool.risk_level == RiskLevel.LOW

    content = await tool.execute(file_path=str(sample_file))
    assert "app_name: NexusAI" in content


@pytest.mark.asyncio
async def test_read_file_tool_not_found() -> None:
    tool = ReadFileTool()
    result = await tool.execute(file_path="/invalid/file.txt")
    assert "Error: File" in result
    assert "not found" in result


def test_workspace_tools_registry() -> None:
    registry = ToolRegistry()
    registry.register(ListDirectoryTool())
    registry.register(ReadFileTool())

    assert registry.has_tool("workspace_list_directory")
    assert registry.has_tool("workspace_read_file")

    schemas = registry.get_all_schemas()
    assert len(schemas) == 2
