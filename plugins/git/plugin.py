"""Official Git Workspace Plugin for NexusAI."""
import asyncio
from typing import Any, List
from pydantic import BaseModel, Field
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool

class GitStatusInputSchema(BaseModel):
    """Input schema for git_status tool."""
    pass

class GitStatusTool(BaseTool):
    """Tool running git status in workspace."""
    name = "git_status"
    description = "Checks current Git repository working tree status"
    risk_level = RiskLevel.LOW
    input_schema = GitStatusInputSchema

    async def execute(self, **kwargs: Any) -> str:
        process = await asyncio.create_subprocess_exec(
            "git", "status", "--short",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return stdout.decode("utf-8", errors="replace") or "Working tree clean"

class GitPlugin:
    """Official Git Plugin class."""
    name = "git_plugin"
    version = "0.1.0"
    description = "Provides Git version control tools"

    def get_tools(self) -> List[BaseTool]:
        return [GitStatusTool()]
