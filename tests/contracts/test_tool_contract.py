"""Contract tests for NexusAI BaseTool implementations."""
import pytest
from typing import Type, List
from nexusai.tools.base import BaseTool
from nexusai.tools.system.terminal import TerminalTool
from nexusai.tools.workspace.fs import ReadFileTool, ListDirectoryTool

TOOL_CLASSES: List[Type[BaseTool]] = [
    TerminalTool,
    ReadFileTool,
    ListDirectoryTool,
]

@pytest.mark.parametrize("tool_cls", TOOL_CLASSES)
def test_tool_subclass_contract(tool_cls: Type[BaseTool]) -> None:
    """Contract: Every tool MUST specify name, description, and an execute method."""
    tool_instance = tool_cls()
    assert hasattr(tool_instance, "name") and isinstance(tool_instance.name, str)
    assert hasattr(tool_instance, "description") and isinstance(tool_instance.description, str)
    assert hasattr(tool_instance, "execute")
