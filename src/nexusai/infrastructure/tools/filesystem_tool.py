"""Governed Filesystem Tool adapter with strict canonical path sandbox boundary enforcement."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.tool_registry import ToolMetadata, ToolStatus, ToolTrustLevel
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult


class FilesystemTool(IToolPort):
    """Real filesystem adapter enforcing canonical root path resolution, symlink boundary checks, and size limits."""

    def __init__(
        self,
        sandbox_root: str | Path,
        max_read_bytes: int = 10 * 1024 * 1024,  # 10 MB limit
    ) -> None:
        self.sandbox_root = Path(sandbox_root).resolve()
        self.max_read_bytes = max_read_bytes

        if not self.sandbox_root.exists():
            self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def _resolve_and_validate_path(self, relative_or_abs_path: str | Path) -> Path:
        """Resolve path canonically and assert it resides strictly inside the configured sandbox root."""
        target = Path(relative_or_abs_path)
        if not target.is_absolute():
            target = self.sandbox_root / target

        # Strict canonical resolution checking symlinks and path traversal
        resolved = target.resolve()

        try:
            resolved.relative_to(self.sandbox_root)
        except ValueError:
            raise PermissionError(
                f"Path traversal blocked: target '{resolved}' escapes sandbox root '{self.sandbox_root}'"
            )

        return resolved

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute filesystem operation (read_file, write_file, delete_file)."""
        action = request.parameters.get("action", "read_file")
        rel_path = request.parameters.get("path", "")

        try:
            if not rel_path:
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=False,
                    error_message="Parameter 'path' is required",
                )

            target_path = self._resolve_and_validate_path(rel_path)

            if action == "read_file":
                if not target_path.exists():
                    return ToolExecutionResult(
                        request_id=request.execution_id,
                        tool_name=request.tool_name,
                        success=False,
                        error_message=f"File not found: {rel_path}",
                    )
                if target_path.stat().st_size > self.max_read_bytes:
                    return ToolExecutionResult(
                        request_id=request.execution_id,
                        tool_name=request.tool_name,
                        success=False,
                        error_message=f"File size exceeds max read limit of {self.max_read_bytes} bytes",
                    )
                content = target_path.read_text(encoding="utf-8")
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=True,
                    output=content,
                )

            elif action == "write_file":
                content = request.parameters.get("content", "")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=True,
                    output=f"Successfully wrote {len(content)} bytes to {rel_path}",
                )

            elif action == "delete_file":
                if not target_path.exists():
                    return ToolExecutionResult(
                        request_id=request.execution_id,
                        tool_name=request.tool_name,
                        success=False,
                        error_message=f"File not found for deletion: {rel_path}",
                    )
                target_path.unlink()
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=True,
                    output=f"Successfully deleted {rel_path}",
                )

            else:
                return ToolExecutionResult(
                    request_id=request.execution_id,
                    tool_name=request.tool_name,
                    success=False,
                    error_message=f"Unknown filesystem action: {action}",
                )

        except PermissionError as err:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=str(err),
            )
        except Exception as err:
            return ToolExecutionResult(
                request_id=request.execution_id,
                tool_name=request.tool_name,
                success=False,
                error_message=f"Filesystem operation error: {err}",
            )


def get_filesystem_tool_metadata() -> ToolMetadata:
    """Return ToolMetadata for FilesystemTool."""
    return ToolMetadata(
        tool_id="filesystem_tool",
        name="Filesystem Tool",
        version="1.0.0",
        description="Governed sandboxed filesystem operations",
        capabilities=frozenset({ToolCapability.FILE_READ, ToolCapability.FILE_WRITE, ToolCapability.FILE_DELETE}),
        status=ToolStatus.ENABLED,
        trust_level=ToolTrustLevel.BUILTIN,
    )
