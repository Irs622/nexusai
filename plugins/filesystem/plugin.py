"""Official File System Plugin for NexusAI."""
from typing import List
from nexusai.tools.base import BaseTool
from nexusai.tools.workspace.fs import ReadFileTool, ListDirectoryTool

class FileSystemPlugin:
    name = "filesystem_plugin"
    version = "0.1.0"
    description = "Provides file system workspace tools"

    def get_tools(self) -> List[BaseTool]:
        return [ReadFileTool(), ListDirectoryTool()]
