"""Official Calculator Tool Plugin for NexusAI."""
from typing import List
from pydantic import BaseModel, Field
from nexusai.tools.base import BaseTool

class CalculatorInput(BaseModel):
    expression: str = Field(description="Math expression to evaluate, e.g. '12 * 4'")

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate mathematical expression"
    args_schema = CalculatorInput

    async def execute(self, expression: str) -> str:
        try:
            allowed_chars = set("0123456789+-*/(). ")
            if not set(expression).issubset(allowed_chars):
                return "Error: Expression contains forbidden characters"
            result = eval(expression, {"__builtins__": {}})
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {e}"

class CalculatorPlugin:
    name = "calculator_plugin"
    version = "0.1.0"
    description = "Provides mathematical calculator tools"

    def get_tools(self) -> List[BaseTool]:
        return [CalculatorTool()]
