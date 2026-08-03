"""Abstract Base Classes for Model Providers in NexusAI."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from nexusai.core.annotations import stable, experimental

@stable
class BaseModelProvider(ABC):
    """Abstract Base Class enforced for all model providers (OpenAI, Claude, Ollama, etc.)."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send chat messages and tool definitions to the LLM model."""
        ...

@stable
class ChatProvider(BaseModelProvider):
    """Specialized interface for Chat LLM Providers."""
    pass

@experimental
class EmbeddingProvider(ABC):
    """Interface for Vector Embedding Providers."""
    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        ...

@experimental
class SpeechProvider(ABC):
    """Interface for Speech-to-Text & Text-to-Speech Providers."""
    @abstractmethod
    async def synthesize_speech(self, text: str) -> bytes:
        ...

@experimental
class VisionProvider(ABC):
    """Interface for Multimodal Vision Model Providers."""
    @abstractmethod
    async def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        ...
