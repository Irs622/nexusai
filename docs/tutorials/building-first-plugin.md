---
status: stable
audience:
  - plugin-developers
owner:
  - sdk-maintainers
applies_to:
  - plugin-development
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔌 Building Your First Plugin

Learn how to write a custom tool plugin in less than 5 minutes.

---

## Code Example

```python
from pydantic import BaseModel, Field
from nexusai.tools.base import BaseTool

class EchoInput(BaseModel):
    message: str = Field(description="Message string to echo back")

class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Echo back user message"
    args_schema = EchoInput

    async def execute(self, message: str) -> str:
        return f"Echo: {message}"
```
