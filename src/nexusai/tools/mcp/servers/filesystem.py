"""Built-in Filesystem MCP Server providing sandboxed file operations."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import time
from typing import Any

from nexusai.tools.mcp.servers.base import McpServerBase


class FilesystemMcpServer(McpServerBase):
    """MCP Server exposing secure, sandboxed filesystem tools within a designated root folder."""

    def __init__(self, root_dir: str | Path = ".") -> None:
        super().__init__(
            name="nexus-filesystem",
            version="1.0.0",
            description="NexusAI Sandboxed Filesystem MCP Server",
        )
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._register_filesystem_tools()

    def _resolve_safe_path(self, target_path: str) -> Path:
        """Resolve path and assert that it remains strictly inside root_dir boundary."""
        # Handle relative or absolute paths against root_dir
        cleaned = target_path.strip().lstrip("/")
        resolved = (self.root_dir / cleaned).resolve()

        try:
            resolved.relative_to(self.root_dir)
        except ValueError as err:
            raise PermissionError(
                f"Path traversal denied: '{target_path}' escapes sandbox root '{self.root_dir}'"
            ) from err

        return resolved

    def _register_filesystem_tools(self) -> None:
        # 1. read_file
        self.register_tool(
            name="read_file",
            description="Read the UTF-8 text contents of a file inside the sandboxed workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file within workspace",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read (default 1MB)",
                        "default": 1048576,
                    },
                },
                "required": ["path"],
            },
            handler=self._handle_read_file,
        )

        # 2. write_file
        self.register_tool(
            name="write_file",
            description="Write text contents to a file, creating parent directories if necessary.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file within workspace",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write into file",
                    },
                },
                "required": ["path", "content"],
            },
            handler=self._handle_write_file,
        )

        # 3. list_directory
        self.register_tool(
            name="list_directory",
            description="List entries in a directory with file types and sizes.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path of directory to list (default '.')",
                        "default": ".",
                    }
                },
            },
            handler=self._handle_list_directory,
        )

        # 4. get_file_info
        self.register_tool(
            name="get_file_info",
            description="Get metadata information about a file or directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file or directory",
                    }
                },
                "required": ["path"],
            },
            handler=self._handle_get_file_info,
        )

        # 5. search_files
        self.register_tool(
            name="search_files",
            description="Search for files matching a glob pattern inside a directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '*.py' or '**/*.json')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Starting directory path (default '.')",
                        "default": ".",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matched files to return (default 100)",
                        "default": 100,
                    },
                },
                "required": ["pattern"],
            },
            handler=self._handle_search_files,
        )

    async def _handle_read_file(self, args: dict[str, Any]) -> str:
        safe_path = self._resolve_safe_path(args["path"])
        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: '{args['path']}'")
        if not safe_path.is_file():
            raise IsADirectoryError(f"Target is a directory, not a file: '{args['path']}'")

        max_bytes = int(args.get("max_bytes", 1048576))
        file_size = safe_path.stat().st_size
        if file_size > max_bytes:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds limit ({max_bytes} bytes)"
            )

        return safe_path.read_text(encoding="utf-8")

    async def _handle_write_file(self, args: dict[str, Any]) -> str:
        safe_path = self._resolve_safe_path(args["path"])
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        safe_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to '{args['path']}'"

    async def _handle_list_directory(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        dir_path = self._resolve_safe_path(args.get("path", "."))
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: '{args.get('path', '.')}'")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Target is not a directory: '{args.get('path', '.')}'")

        entries: list[dict[str, Any]] = []
        for item in sorted(dir_path.iterdir()):
            rel = str(item.relative_to(self.root_dir))
            is_file = item.is_file()
            size = item.stat().st_size if is_file else 0
            entries.append(
                {
                    "name": item.name,
                    "path": rel,
                    "type": "file" if is_file else "directory",
                    "size_bytes": size,
                }
            )
        return entries

    async def _handle_get_file_info(self, args: dict[str, Any]) -> dict[str, Any]:
        target = self._resolve_safe_path(args["path"])
        if not target.exists():
            raise FileNotFoundError(f"Path does not exist: '{args['path']}'")

        stat = target.stat()
        return {
            "name": target.name,
            "path": str(target.relative_to(self.root_dir)),
            "exists": True,
            "is_file": target.is_file(),
            "is_directory": target.is_dir(),
            "size_bytes": stat.st_size,
            "modified_time_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
            "created_time_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_ctime)),
        }

    async def _handle_search_files(self, args: dict[str, Any]) -> list[str]:
        base_dir = self._resolve_safe_path(args.get("path", "."))
        pattern = str(args.get("pattern", "*"))
        max_results = int(args.get("max_results", 100))

        if not base_dir.exists() or not base_dir.is_dir():
            raise NotADirectoryError(f"Search starting directory not found: '{args.get('path')}'")

        matches: list[str] = []
        for matched in base_dir.glob(pattern):
            if matched.is_file():
                matches.append(str(matched.relative_to(self.root_dir)))
                if len(matches) >= max_results:
                    break

        return matches


def main() -> None:
    """CLI entry point for running Filesystem MCP Server."""
    parser = argparse.ArgumentParser(description="NexusAI Sandboxed Filesystem MCP Server")
    parser.add_argument(
        "--root",
        type=str,
        default=os.environ.get("NEXUS_FS_ROOT", "storage"),
        help="Root directory for sandboxed file operations (default: storage)",
    )
    args = parser.parse_args()

    server = FilesystemMcpServer(root_dir=args.root)
    server.log(f"Initialized with root directory: {server.root_dir}")
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
