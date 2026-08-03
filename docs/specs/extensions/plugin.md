---
status: draft
audience:
  - plugin-developers
  - core-developers
owner:
  - sdk-maintainers
applies_to:
  - plugin-system
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔌 Plugin Specification

## 1. Overview

This document specifies the contract for external **NexusAI Plugins**. A plugin is a modular package containing custom tools, event listeners, or model provider adapters.

---

## 2. Plugin Structure Specification

A valid NexusAI plugin package MUST contain a `plugin.json` manifest or a `NexusAIPlugin` entrypoint:

```json
{
  "name": "nexusai-plugin-weather",
  "version": "0.1.0",
  "nexusai_sdk_version": ">=0.1.0",
  "author": "NexusAI Community",
  "description": "Weather forecasting tool plugin",
  "entry_point": "nexusai_plugin_weather:WeatherPlugin"
}
```

---

## 3. Plugin Class Interface (`BasePlugin`)

```python
from abc import ABC, abstractmethod
from typing import List
from nexusai.tools.base import BaseTool

class BasePlugin(ABC):
    name: str
    version: str
    description: str

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """Return list of tool instances provided by this plugin."""
        pass

    async def on_load((self) -> None:
        """Lifecycle hook executed when plugin is loaded into runtime."""
        pass

    async def on_unload(self) -> None:
        """Lifecycle hook executed when plugin is unloaded."""
        pass
```
