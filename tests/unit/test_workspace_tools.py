"""
Unit tests for Workspace File System Tools.
"""

from pathlib import Path

import pytest

from nexusai.security.guard import RiskLevel
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ListDirectoryTool, ReadFileTool, WriteFileTool


@pytest.mark.asyncio
async def test_list_directory_tool(tmp_path: Path) -> None:
    # Create sample files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.py").write_text("print('hello')")
    (tmp_path / "subdir").mkdir()

    tool = ListDirectoryTool(workspace_root=tmp_path)
    assert tool.name == "workspace_list_directory"
    assert tool.risk_level == RiskLevel.LOW

    result = await tool.execute(path=".")
    assert isinstance(result, list)
    assert result == ["file1.txt", "file2.py", "subdir"]


@pytest.mark.asyncio
async def test_list_directory_non_existent_path(tmp_path: Path) -> None:
    tool = ListDirectoryTool(workspace_root=tmp_path)
    result = await tool.execute(path="non_existent_path_12345")
    assert "Error:" in str(result)


@pytest.mark.asyncio
async def test_read_file_tool(tmp_path: Path) -> None:
    sample_file = tmp_path / "config.yaml"
    sample_file.write_text("app_name: NexusAI\nversion: 0.1.0")

    tool = ReadFileTool(workspace_root=tmp_path)
    assert tool.name == "workspace_read_file"
    assert tool.risk_level == RiskLevel.LOW

    content = await tool.execute(file_path="config.yaml")
    assert "app_name: NexusAI" in content


@pytest.mark.asyncio
async def test_read_file_tool_not_found(tmp_path: Path) -> None:
    tool = ReadFileTool(workspace_root=tmp_path)
    result = await tool.execute(file_path="invalid_file_not_found.txt")
    assert "Error: File" in result
    assert "not found" in result


@pytest.mark.asyncio
async def test_workspace_path_traversal_denied(tmp_path: Path) -> None:
    tool = ReadFileTool(workspace_root=tmp_path)
    # Attempt directory traversal escape
    result = await tool.execute(file_path="../../etc/passwd")
    assert "Path traversal denied" in result


@pytest.mark.asyncio
async def test_workspace_symlink_escape_denied(tmp_path: Path) -> None:
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("classified")

    evil_link = tmp_path / "evil_symlink.txt"
    try:
        evil_link.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    tool = ReadFileTool(workspace_root=tmp_path)
    result = await tool.execute(file_path="evil_symlink.txt")
    assert "Path traversal denied" in result


@pytest.mark.asyncio
async def test_workspace_write_file_success(tmp_path: Path) -> None:
    tool = WriteFileTool(workspace_root=tmp_path)
    result = await tool.execute(file_path="sub/test.txt", content="hello world")
    assert "Successfully wrote" in result

    saved_file = tmp_path / "sub" / "test.txt"
    assert saved_file.is_file()
    assert saved_file.read_text() == "hello world"


@pytest.mark.asyncio
async def test_workspace_write_file_escape_denied(tmp_path: Path) -> None:
    tool = WriteFileTool(workspace_root=tmp_path)
    result = await tool.execute(file_path="../../etc/cron.d/job", content="malicious")
    assert "Path traversal denied" in result


def test_workspace_tools_registry() -> None:
    registry = ToolRegistry()
    registry.register(ListDirectoryTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())

    assert registry.has_tool("workspace_list_directory")
    assert registry.has_tool("workspace_read_file")
    assert registry.has_tool("workspace_write_file")

    schemas = registry.get_all_schemas()
    assert len(schemas) == 3
