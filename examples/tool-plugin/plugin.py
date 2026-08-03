"""Example custom tool plugin for NexusAI."""
from pydantic import BaseModel, Field
from nexusai.tools.base import BaseTool

class GreetingInput(BaseModel):
    name: str = Field(description="Name to greet")

class GreetingTool(BaseTool):
    name = "greeting_tool"
    description = "Generate a custom personalized greeting"
    args_schema = GreetingInput

    async def execute(self, name: str) -> str:
        return f"Greetings, {name}! Welcome to NexusAI."
