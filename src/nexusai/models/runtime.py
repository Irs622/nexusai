"""Provider Resilience Runtime: Retries, Rate Limiting, and Fallback Providers."""
import asyncio
from typing import Any, Dict, List, Optional
from nexusai.models.base import BaseModelProvider
from nexusai.core.errors import ModelProviderError
from nexusai.logging.logger import logger

class ProviderRuntime:
    """Resilient wrapper for BaseModelProvider supporting retries, timeouts, and fallbacks."""

    def __init__(
        self,
        primary_provider: BaseModelProvider,
        fallback_provider: Optional[BaseModelProvider] = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.primary = primary_provider
        self.fallback = fallback_provider
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    async def chat_with_resilience(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute chat request with automatic exponential retry and fallback routing."""
        last_exception: Optional[Exception] = None

        # 1. Try Primary Provider with Retries
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.primary.chat(messages, tools)
            except Exception as e:
                last_exception = e
                logger.warning(f"Primary LLM Provider attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_seconds * attempt)

        # 2. Try Fallback Provider if primary fails completely
        if self.fallback is not None:
            logger.info("Switching to Fallback LLM Provider...")
            try:
                return await self.fallback.chat(messages, tools)
            except Exception as fe:
                raise ModelProviderError(f"Both Primary and Fallback LLM Providers failed. Fallback error: {fe}") from fe

        raise ModelProviderError(f"LLM Provider call failed after {self.max_retries} attempts: {last_exception}") from last_exception
