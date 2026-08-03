"""Subprocess Plugin Execution Isolation Sandbox with Output Size Limits & Process Cleanup."""
import sys
import os
import asyncio
import subprocess
from typing import Any, Dict
from nexusai.core.errors import ToolExecutionError

class SubprocessPluginRunner:
    """Executes plugin tools in isolated subprocesses with timeout, output size limit, and process cleanup."""

    def __init__(self, timeout_seconds: float = 30.0, max_output_bytes: int = 1_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    async def execute_isolated_code(self, script_code: str, kwargs: Dict[str, Any]) -> str:
        """Run Python code block in isolated subprocess with environment scrubbing, process cleanup, and stdout capping."""
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        }

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=clean_env,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                    await asyncio.sleep(0.1)
                    if process.returncode is None:
                        process.kill()
                except Exception:
                    pass
                raise ToolExecutionError(f"Subprocess plugin execution timed out after {self.timeout_seconds} seconds")

            if process.returncode != 0:
                err_msg = stderr_bytes.decode("utf-8", errors="replace")[:2000]
                raise ToolExecutionError(f"Subprocess plugin failed with exit code {process.returncode}: {err_msg}")

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            if len(stdout_str) > self.max_output_bytes:
                stdout_str = stdout_str[:self.max_output_bytes] + "\n... [Output truncated by Sandbox limit]"

            return stdout_str
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(f"Subprocess execution error: {e}") from e
