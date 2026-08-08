"""Streaming Token Execution Runtime for LLM Model Providers."""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

from nexusai.models.base import BaseModelProvider


class StreamingProviderRuntime:
    """Provides chunk-by-chunk token streaming abstractions over BaseModelProvider."""

    def __init__(self, provider: BaseModelProvider) -> None:
        self.provider = provider

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Simulate chunk-by-chunk streaming tokens from provider response."""
        full_response = await self.provider.chat(messages, tools)
        content = full_response.get("content", "")

        # Stream word by word asynchronously
        words = content.split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.01)
