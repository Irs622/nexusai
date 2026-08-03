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
last_reviewed: 2026-08-04
---

# 🤖 Model Provider Specification & Provider SDK Foundation

## 1. Abstract Interface (`BaseProvider`)

All vendor LLM adapters in NexusAI MUST inherit from `BaseProvider` (`nexusai.providers.base.BaseProvider`):

```python
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from nexusai.providers.models import (
    ChatRequest, ChatResponse, EmbeddingResult,
    ModelInfo, ProviderHealth, ProviderMetadata
)

class BaseProvider(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata: ...

    @property
    def id(self) -> str:
        return self.metadata.provider_id

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]: ...

    @abstractmethod
    async def embeddings(self, texts: list[str], model: str | None = None, **kwargs: Any) -> EmbeddingResult: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth: ...

    async def initialize(self) -> None: pass
    async def shutdown(self) -> None: pass
```

---

## 2. Standardized Data Models (`ChatRequest`, `ChatResponse`, `JSONSchema`)

Every adapter MUST translate between vendor-specific payloads and NexusAI canonical SDK models:

### Chat Message Contracts
- `MessageRole` (`SYSTEM`, `USER`, `ASSISTANT`, `TOOL`, `DEVELOPER`)
- `ChatMessage` (role, content, name, tool_calls, tool_call_id)
- `ToolSchema` (name, description, parameters: `JSONSchema`, strict)
- `ChatChoice` (index, message, finish_reason)
- `ChatResponse` (choices: `list[ChatChoice]`, usage, model, provider, trace)
  - `response.primary_choice()` returns the top choice candidate.

---

## 3. Provider Architecture Stack & Lifecycle Management

- **`ProviderRegistry`**: Pure instance registration, lookup, and default provider selection.
- **`ProviderManager`**: Manages lifecycle (`initialize_all`, `shutdown_all`), concurrent health checks (`health_check_all`), and capability queries (`find_by_capability`, `supports`).
- **`ProviderRouter`**: Executes policy-based provider selection (`select_provider`, `rank_providers`) matching required capabilities, health, cost, and priorities.
