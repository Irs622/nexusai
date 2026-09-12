"""Workspace File System Tools with Workspace-Root Containment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nexusai.runtime.execution_semantics import ExecutionSemantics
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool


class ListDirectoryInputSchema(BaseModel):
    """Input schema for workspace_list_directory tool."""

    path: str = Field(default=".", description="Directory path to list files and folders")


class ListDirectoryTool(BaseTool):
    """Tool listing contents of a directory with workspace-root containment."""

    name = "workspace_list_directory"
    description = "Lists files and directories at the specified path within workspace."
    risk_level = RiskLevel.LOW
    execution_semantics = ExecutionSemantics.IDEMPOTENT
    input_schema = ListDirectoryInputSchema

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        )

    def _resolve_safe_path(self, target_path: str) -> Path:
        """Resolve and verify path is contained strictly within workspace root."""
        p = Path(target_path).expanduser()
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self.workspace_root / p).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as err:
            raise PermissionError(
                f"Path traversal denied: '{target_path}' escapes workspace root '{self.workspace_root}'"
            ) from err

        return resolved

    async def execute(self, path: str = ".", **kwargs: Any) -> list[str] | str:
        """List files and directories safely at target path within workspace root."""
        try:
            target = self._resolve_safe_path(path)
        except PermissionError as pe:
            return f"Error: {pe}"
        except Exception as e:
            return f"Error resolving directory '{path}': {e}"

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
    """Tool reading text contents of a file with workspace-root containment."""

    name = "workspace_read_file"
    description = "Reads and returns text content from a specified file path within workspace."
    risk_level = RiskLevel.LOW
    execution_semantics = ExecutionSemantics.IDEMPOTENT
    input_schema = ReadFileInputSchema

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        )

    def _resolve_safe_path(self, target_path: str) -> Path:
        """Resolve and verify path is contained strictly within workspace root."""
        p = Path(target_path).expanduser()
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self.workspace_root / p).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as err:
            raise PermissionError(
                f"Path traversal denied: '{target_path}' escapes workspace root '{self.workspace_root}'"
            ) from err

        return resolved

    async def execute(self, file_path: str, **kwargs: Any) -> str:
        """Read file contents safely within workspace root."""
        try:
            target = self._resolve_safe_path(file_path)
        except PermissionError as pe:
            return f"Error: {pe}"
        except Exception as e:
            return f"Error resolving file '{file_path}': {e}"

        try:
            if not target.exists():
                return f"Error: File '{file_path}' not found."
            if not target.is_file():
                return f"Error: Path '{file_path}' is a directory, not a file."

            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file '{file_path}': {e}"


class WriteFileInputSchema(BaseModel):
    """Input schema for workspace_write_file tool."""

    file_path: str = Field(..., description="File path to write text contents to")
    content: str = Field(..., description="Text content to write into the file")


class WriteFileTool(BaseTool):
    """Tool writing text contents to a file with workspace-root containment."""

    name = "workspace_write_file"
    description = "Writes text content to a specified file path within workspace."
    risk_level = RiskLevel.MEDIUM
    input_schema = WriteFileInputSchema

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        )

    def _resolve_safe_path(self, target_path: str) -> Path:
        """Resolve and verify path is contained strictly within workspace root."""
        p = Path(target_path).expanduser()
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self.workspace_root / p).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as err:
            raise PermissionError(
                f"Path traversal denied: '{target_path}' escapes workspace root '{self.workspace_root}'"
            ) from err

        return resolved

    async def execute(self, file_path: str, content: str = "", **kwargs: Any) -> str:
        """Write file contents safely within workspace root."""
        try:
            target = self._resolve_safe_path(file_path)
        except PermissionError as pe:
            return f"Error: {pe}"
        except Exception as e:
            return f"Error resolving file '{file_path}': {e}"

        try:
            if target.exists() and target.is_dir():
                return f"Error: Path '{file_path}' is a directory, cannot overwrite with file."

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} characters to '{file_path}'."
        except Exception as e:
            return f"Error writing file '{file_path}': {e}"
