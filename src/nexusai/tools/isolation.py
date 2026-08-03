"""Subprocess Plugin Execution Isolation Sandbox with Truncation Metadata & Process Cleanup."""
import sys
import os
import asyncio
import subprocess
from typing import Any, Dict, Optional
from nexusai.core.errors import ToolExecutionError

class SubprocessPluginRunner:
    """Executes plugin tools in isolated subprocesses with timeout, truncation metadata, and process cleanup."""

    def __init__(self, timeout_seconds: float = 30.0, max_output_bytes: int = 1_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    async def execute_isolated_code(self, script_code: str, kwargs: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run Python code block in isolated subprocess returning output and truncation metadata."""
        subprocess_env = env if env is not None else dict(os.environ)

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                script_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=subprocess_env,
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
            original_size = len(stdout_str)
            is_truncated = original_size > self.max_output_bytes
            
            returned_output = stdout_str[:self.max_output_bytes] if is_truncated else stdout_str
            returned_size = len(returned_output)

            return {
                "output": returned_output,
                "truncated": is_truncated,
                "original_size": original_size,
                "returned_size": returned_size,
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(f"Subprocess execution error: {e}") from e
