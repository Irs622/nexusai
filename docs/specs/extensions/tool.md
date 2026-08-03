---
status: stable
audience:
  - plugin-developers
  - core-developers
owner:
  - core-team
applies_to:
  - tool-system
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🛠️ Tool Specification

## 1. Abstract Tool Base Class (`BaseTool`)

Every tool in NexusAI MUST inherit from `BaseTool`:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Type
from pydantic import BaseModel

class BaseTool(ABC):
    name: str
    description: str
    args_schema: Optional[Type[BaseModel]] = None

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute tool action with validated kwargs and return string or dict result."""
        pass
```

---

## 2. Risk Classification Metadata

Tools MAY specify a risk level attribute used by `SecurityGuard`:
- `LOW`: Safe read-only operations (e.g., getting current time, reading public docs).
- `MEDIUM`: Reversible system actions (e.g., opening a browser tab, creating a temporary file).
- `HIGH`: System configuration modifications (e.g., editing config files, sending emails).
- `CRITICAL`: Potentially destructive operations (e.g., executing shell scripts, deleting files).
