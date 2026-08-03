"""Tool execution latency benchmark for NexusAI."""
import time
import asyncio
from nexusai.tools.workspace.fs import FileSystemReadTool

async def measure_tool_latency() -> float:
    tool = FileSystemReadTool()
    start_time = time.perf_counter()
    await tool.execute(path="pyproject.toml")
    end_time = time.perf_counter()
    return (end_time - start_time) * 1000 # convert to ms

if __name__ == "__main__":
    latency_ms = asyncio.run(measure_tool_latency())
    print(f"Tool Execution Latency: {latency_ms:.2f} ms")
