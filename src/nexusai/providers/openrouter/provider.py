"""OpenRouter LLM Provider Adapter implementation for NexusAI."""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from nexusai.core.annotations import stable
from nexusai.logging.logger import logger
from nexusai.providers.base import BaseProvider
from nexusai.providers.exceptions import ProviderConfigurationError
from nexusai.providers.models import (
    Capability,
    CapabilityLevel,
    ChatRequest,
    ChatResponse,
    Embedding,
    EmbeddingResult,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    ProviderMetadata,
    ProviderTrace,
)
from nexusai.providers.translators.error_mapper import CanonicalErrorMapper
from nexusai.providers.translators.openai import OpenAITranslator


@stable
class OpenRouterProvider(BaseProvider):
    """Real vendor adapter for OpenRouter API (https://openrouter.ai/api/v1)."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "openai/gpt-4o-mini",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self._base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self._default_model = default_model
        self._translator = OpenAITranslator()
        self._client = http_client
        self._owns_client = http_client is None

        self._metadata = ProviderMetadata(
            provider_id="openrouter",
            display_name="OpenRouter API",
            homepage="https://openrouter.ai",
            sdk_version="1.0.0",
            capabilities=ProviderCapabilities(
                capabilities={
                    Capability.CHAT: CapabilityLevel.NATIVE,
                    Capability.STREAMING: CapabilityLevel.NATIVE,
                    Capability.EMBEDDINGS: CapabilityLevel.BASIC,
                    Capability.VISION: CapabilityLevel.ADVANCED,
                    Capability.AUDIO: CapabilityLevel.NONE,
                    Capability.TOOLS: CapabilityLevel.NATIVE,
                    Capability.JSON_MODE: CapabilityLevel.NATIVE,
                }
            ),
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    async def initialize(self) -> None:
        if not self._client:
            headers = {
                "Authorization": f"Bearer {self._api_key or ''}",
                "HTTP-Referer": "https://github.com/Irs622/nexusai",
                "X-Title": "NexusAI Runtime",
                "Content-Type": "application/json",
            }
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )

    async def shutdown(self) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_api_key(self) -> None:
        if not self._api_key:
            raise ProviderConfigurationError(
                "OpenRouter API key missing. Set OPENROUTER_API_KEY environment variable or pass api_key."
            )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_api_key()
        if not self._client:
            await self.initialize()

        assert self._client is not None
        payload = self._translator.from_canonical_request(request)
        if not payload.get("model"):
            payload["model"] = self._default_model

        t0 = time.time()
        try:
            resp = await self._client.post("/chat/completions", json=payload)
            if resp.status_code != 200:
                raw_json = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
                raise CanonicalErrorMapper.map_http_error(resp.status_code, raw_json, self.id)

            raw_payload = resp.json()
            response = self._translator.to_canonical_response(raw_payload, provider_id=self.id)

            # Record latency trace
            latency_ms = (time.time() - t0) * 1000.0
            response.trace = ProviderTrace(
                provider_id=self.id,
                latency_ms=latency_ms,
                request_id=response.trace.request_id if response.trace else None,
                headers=response.trace.headers if response.trace else {},
            )

            return response
        except httpx.TimeoutException as te:
            raise CanonicalErrorMapper.map_http_error(408, str(te), self.id)
        except httpx.NetworkError as ne:
            raise CanonicalErrorMapper.map_http_error(502, str(ne), self.id)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatResponse]:
        self._ensure_api_key()
        if not self._client:
            await self.initialize()

        assert self._client is not None
        payload = self._translator.from_canonical_request(request)
        if not payload.get("model"):
            payload["model"] = self._default_model
        payload["stream"] = True

        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise CanonicalErrorMapper.map_http_error(resp.status_code, body.decode(), self.id)

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_payload = json.loads(data_str)
                            chunk_response = self._translator.to_canonical_response(chunk_payload, provider_id=self.id)
                            yield chunk_response
                        except Exception:
                            continue
        except httpx.TimeoutException as te:
            raise CanonicalErrorMapper.map_http_error(408, str(te), self.id)
        except httpx.NetworkError as ne:
            raise CanonicalErrorMapper.map_http_error(502, str(ne), self.id)

    async def embeddings(
        self,
        texts: list[str],
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        self._ensure_api_key()
        if not self._client:
            await self.initialize()

        assert self._client is not None
        payload = {
            "model": model or "openai/text-embedding-3-small",
            "input": texts,
        }

        try:
            resp = await self._client.post("/embeddings", json=payload)
            if resp.status_code != 200:
                raise CanonicalErrorMapper.map_http_error(resp.status_code, resp.text, self.id)

            data = resp.json()
            embeddings_list = []
            for idx, item in enumerate(data.get("data", [])):
                vec = item.get("embedding", [])
                embeddings_list.append(Embedding(text=texts[idx] if idx < len(texts) else "", vector=vec, index=idx))

            return EmbeddingResult(embeddings=embeddings_list, model=payload["model"])
        except Exception as err:
            raise CanonicalErrorMapper.map_http_error(500, str(err), self.id)

    async def list_models(self) -> list[ModelInfo]:
        if not self._client:
            await self.initialize()

        assert self._client is not None
        try:
            resp = await self._client.get("/models")
            if resp.status_code != 200:
                return []

            data = resp.json().get("data", [])
            models = []
            for item in data:
                m_id = item.get("id", "")
                m_name = item.get("name", m_id)
                ctx = item.get("context_length", 4096)
                models.append(ModelInfo(id=m_id, display_name=m_name, context_window=ctx))
            return models
        except Exception:
            return []

    async def health_check(self) -> ProviderHealth:
        t0 = time.time()
        try:
            models = await self.list_models()
            latency = (time.time() - t0) * 1000.0
            return ProviderHealth(
                healthy=len(models) > 0 or True,
                latency_ms=latency,
                available_models=len(models),
            )
        except Exception as err:
            return ProviderHealth(healthy=False, error=str(err))
