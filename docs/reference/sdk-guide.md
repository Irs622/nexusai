---
status: stable
audience:
  - plugin-developers
owner:
  - sdk-maintainers
applies_to:
  - plugin-sdk
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔌 Plugin SDK Developer Guide

This guide walks you through building custom tools and extending NexusAI using the Plugin SDK.

---

## 🛠️ Step 1: Create a Custom Tool

To create a new tool, inherit from `BaseTool` and define your parameter schema using Pydantic:

```python
from pydantic import BaseModel, Field
from nexusai.tools.base import BaseTool

class CalculatorInput(BaseModel):
    expression: str = Field(description="Mathematical expression to evaluate, e.g. '2 + 2'")

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate mathematical expressions safely"
    args_schema = CalculatorInput

    async def execute(self, expression: str) -> str:
        try:
            # Safe evaluation logic
            result = eval(expression, {"__builtins__": {}})
            return f"Result: {result}"
        except Exception as e:
            return f"Error evaluating expression: {e}"
```

---

## 📥 Step 2: Register Tool with Registry

Register your tool instance with the global `ToolRegistry`:

```python
from nexusai.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(CalculatorTool())
```
