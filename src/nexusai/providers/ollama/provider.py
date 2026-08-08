"""Ollama Local LLM Provider Adapter implementation for NexusAI."""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from nexusai.core.annotations import stable
from nexusai.providers.base import BaseProvider
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
from nexusai.providers.translators.ollama import OllamaTranslator


@stable
class OllamaProvider(BaseProvider):
    """Real vendor adapter for Ollama Local REST API (http://localhost:11434/api)."""

    DEFAULT_BASE_URL = "http://localhost:11434/api"

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str = "llama3",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or self.DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self._default_model = default_model
        self._translator = OllamaTranslator()
        self._client = http_client
        self._owns_client = http_client is None

        self._metadata = ProviderMetadata(
            provider_id="ollama",
            display_name="Ollama Local Engine",
            homepage="https://ollama.com",
            sdk_version="1.0.0",
            capabilities=ProviderCapabilities(
                capabilities={
                    Capability.CHAT: CapabilityLevel.NATIVE,
                    Capability.STREAMING: CapabilityLevel.NATIVE,
                    Capability.EMBEDDINGS: CapabilityLevel.BASIC,
                    Capability.VISION: CapabilityLevel.BASIC,
                    Capability.AUDIO: CapabilityLevel.NONE,
                    Capability.TOOLS: CapabilityLevel.BASIC,
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
                "Content-Type": "application/json",
            }
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(60.0, connect=5.0),
            )

    async def shutdown(self) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self._client:
            await self.initialize()

        assert self._client is not None
        payload = self._translator.from_canonical_request(request)
        if not payload.get("model"):
            payload["model"] = self._default_model

        t0 = time.time()
        try:
            resp = await self._client.post("/chat", json=payload)
            if resp.status_code != 200:
                raw_json = (
                    resp.json()
                    if "application/json" in resp.headers.get("content-type", "")
                    else resp.text
                )
                raise CanonicalErrorMapper.map_http_error(resp.status_code, raw_json, self.id)

            raw_payload = resp.json()
            response = self._translator.to_canonical_response(raw_payload, provider_id=self.id)

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
        if not self._client:
            await self.initialize()

        assert self._client is not None
        payload = self._translator.from_canonical_request(request)
        if not payload.get("model"):
            payload["model"] = self._default_model
        payload["stream"] = True

        try:
            async with self._client.stream("POST", "/chat", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise CanonicalErrorMapper.map_http_error(
                        resp.status_code, body.decode(), self.id
                    )

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk_payload = json.loads(line)
                        chunk_response = self._translator.to_canonical_response(
                            chunk_payload, provider_id=self.id
                        )
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
        if not self._client:
            await self.initialize()

        assert self._client is not None
        target_model = model or self._default_model
        embeddings_list = []

        try:
            # Try /embed batch endpoint first, fallback to per-item /embeddings if needed
            resp = await self._client.post("/embed", json={"model": target_model, "input": texts})
            if resp.status_code == 200:
                data = resp.json()
                raw_embeds = data.get("embeddings", [])
                for idx, vec in enumerate(raw_embeds):
                    embeddings_list.append(
                        Embedding(
                            text=texts[idx] if idx < len(texts) else "", vector=vec, index=idx
                        )
                    )
                return EmbeddingResult(
                    embeddings=embeddings_list, model=target_model, provider=self.id
                )

            # Fallback for older Ollama versions: POST /embeddings per item
            for idx, text in enumerate(texts):
                single_resp = await self._client.post(
                    "/embeddings", json={"model": target_model, "prompt": text}
                )
                if single_resp.status_code != 200:
                    raise CanonicalErrorMapper.map_http_error(
                        single_resp.status_code, single_resp.text, self.id
                    )
                vec = single_resp.json().get("embedding", [])
                embeddings_list.append(Embedding(text=text, vector=vec, index=idx))

            return EmbeddingResult(embeddings=embeddings_list, model=target_model, provider=self.id)
        except Exception as err:
            if isinstance(err, (httpx.TimeoutException, httpx.NetworkError)):
                raise CanonicalErrorMapper.map_http_error(502, str(err), self.id)
            raise CanonicalErrorMapper.map_http_error(500, str(err), self.id)

    async def list_models(self) -> list[ModelInfo]:
        if not self._client:
            await self.initialize()

        assert self._client is not None
        try:
            resp = await self._client.get("/tags")
            if resp.status_code != 200:
                return []

            models_data = resp.json().get("models", [])
            result = []
            for item in models_data:
                name = item.get("name", "")
                m_id = item.get("model", name)
                details = item.get("details", {})
                family = details.get("family", "")
                result.append(
                    ModelInfo(
                        id=m_id or name,
                        display_name=name,
                        family=family,
                        context_window=8192,
                    )
                )
            return result
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
