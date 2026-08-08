"""
Async AppleScript execution engine using osascript.
"""

import asyncio

from nexusai.core.errors import ToolExecutionError


async def execute_applescript(script: str) -> str:
    """Execute an AppleScript string via osascript subprocess asynchronously.

    Args:
        script: The AppleScript code to execute.

    Returns:
        Stripped stdout output from osascript.

    Raises:
        ToolExecutionError: If osascript fails or returns a non-zero exit code.
    """
    process = await asyncio.create_subprocess_exec(
        "osascript",
        "-e",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_bytes, stderr_bytes = await process.communicate()
    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise ToolExecutionError(
            f"AppleScript execution failed with code {process.returncode}: {stderr_str or stdout_str}",
            details={
                "script": script,
                "returncode": str(process.returncode),
                "stderr": stderr_str,
            },
        )

    return stdout_str
