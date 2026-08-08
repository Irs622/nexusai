"""
Workspace File System Tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class ListDirectoryInputSchema(BaseModel):
    """Input schema for workspace_list_directory tool."""

    path: str = Field(default=".", description="Directory path to list files and folders")


class ListDirectoryTool(BaseTool):
    """Tool listing contents of a directory."""

    name = "workspace_list_directory"
    description = "Lists files and directories at the specified path."
    risk_level = RiskLevel.LOW
    input_schema = ListDirectoryInputSchema

    async def execute(self, path: str = ".", **kwargs: Any) -> list[str] | str:
        """List files and directories at target path."""
        target = Path(path).expanduser().resolve()
        try:
            if not target.exists():
                return f"Error: Path '{path}' does not exist."
            if not target.is_dir():
                return f"Error: Path '{path}' is a file, not a directory."

            items = [item.name for item in target.iterdir()]
            return sorted(items)
        except Exception as e:
            return f"Error listing directory '{path}': {e}"


class ReadFileInputSchema(BaseModel):
    """Input schema for workspace_read_file tool."""

    file_path: str = Field(..., description="File path to read text contents from")


class ReadFileTool(BaseTool):
    """Tool reading text contents of a file."""

    name = "workspace_read_file"
    description = "Reads and returns text content from a specified file path."
    risk_level = RiskLevel.LOW
    input_schema = ReadFileInputSchema

    async def execute(self, file_path: str, **kwargs: Any) -> str:
        """Read file contents safely."""
        target = Path(file_path).expanduser().resolve()
        try:
            if not target.exists():
                return f"Error: File '{file_path}' not found."
            if not target.is_file():
                return f"Error: Path '{file_path}' is a directory, not a file."

            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file '{file_path}': {e}"
