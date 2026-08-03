"""Subprocess Plugin Execution Isolation Sandbox with Process Cleanup & Environment Scrubbing."""
import sys
import os
import asyncio
import subprocess
from typing import Any, Dict
from nexusai.core.errors import ToolExecutionError

class SubprocessPluginRunner:
    """Executes plugin tools in isolated subprocesses with timeout, environment scrubbing, and cleanup guarantees."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def execute_isolated_code(self, script_code: str, kwargs: Dict[str, Any]) -> str:
        """Run Python code block in isolated subprocess with environment scrubbing and process cleanup."""
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
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
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
                err_msg = stderr.decode("utf-8", errors="replace")
                raise ToolExecutionError(f"Subprocess plugin failed with exit code {process.returncode}: {err_msg}")

            return stdout.decode("utf-8", errors="replace")
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(f"Subprocess execution error: {e}") from e
