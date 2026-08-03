---
status: stable
audience:
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - model-providers
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🤖 Model Provider Specification

## 1. Abstract Interface (`BaseModelProvider`)

All LLM provider adapters MUST inherit from `BaseModelProvider`:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseModelProvider(ABC):
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate LLM response.
        MUST return a dict in standard schema:
        {
          "type": "text" | "tool_call",
          "content": str (if text),
          "tool_name": str (if tool_call),
          "arguments": dict (if tool_call)
        }
        """
        pass
```

---

## 2. Standardized Output Response Schema

To ensure model-agnostic routing, every provider MUST normalize LLM responses into one of two canonical dict schemas:

### Text Response Schema
```json
{
  "type": "text",
  "content": "Hello! How can I assist you with your macOS workspace today?"
}
```

### Tool Call Schema
```json
{
  "type": "tool_call",
  "tool_name": "execute_terminal",
  "arguments": {
    "command": "ls -la ~/Documents"
  }
}
```
