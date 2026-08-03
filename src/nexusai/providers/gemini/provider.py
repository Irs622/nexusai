"""Google Gemini LLM Provider Adapter implementation for NexusAI."""

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
)
from nexusai.providers.translators.error_mapper import CanonicalErrorMapper
from nexusai.providers.translators.gemini import GeminiTranslator


@stable
class GeminiProvider(BaseProvider):
    """Real vendor adapter for Google Gemini REST API (https://generativelanguage.googleapis.com/v1beta)."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "models/gemini-1.5-flash",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._base_url = (base_url or os.getenv("GEMINI_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self._default_model = default_model
        self._translator = GeminiTranslator()
        self._client = http_client
        self._owns_client = http_client is None

        self._metadata = ProviderMetadata(
            provider_id="gemini",
            display_name="Google Gemini API",
            homepage="https://ai.google.dev",
            version="1.0.0",
            capabilities=ProviderCapabilities(
                chat=CapabilityLevel.NATIVE,
                streaming=CapabilityLevel.NATIVE,
                embeddings=CapabilityLevel.NATIVE,
                vision=CapabilityLevel.NATIVE,
                audio=CapabilityLevel.ADVANCED,
                tools=CapabilityLevel.NATIVE,
                json_mode=CapabilityLevel.NATIVE,
                max_context=1000000,
            ),
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    async def initialize(self) -> None:
        if not self._client:
            headers = {"Content-Type": "application/json"}
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
                "Gemini API key missing. Set GEMINI_API_KEY environment variable or pass api_key."
            )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_api_key()
        if not self._client:
            await self.initialize()

        assert self._client is not None
        model_name = request.model or self._default_model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        payload = self._translator.from_canonical_request(request)
        url = f"/{model_name}:generateContent?key={self._api_key}"

        t0 = time.time()
        try:
            resp = await self._client.post(url, json=payload)
            if resp.status_code != 200:
                raw_json = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
                raise CanonicalErrorMapper.map_http_error(resp.status_code, raw_json, self.id)

            raw_payload = resp.json()
            response = self._translator.to_canonical_response(raw_payload, provider_id=self.id)

            latency_ms = (time.time() - t0) * 1000.0
            if response.trace:
                response.trace.latency_ms = latency_ms

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
        model_name = request.model or self._default_model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        payload = self._translator.from_canonical_request(request)
        url = f"/{model_name}:streamGenerateContent?alt=sse&key={self._api_key}"

        try:
            async with self._client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise CanonicalErrorMapper.map_http_error(resp.status_code, body.decode(), self.id)

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
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
        model_name = model or "models/text-embedding-004"
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"/{model_name}:embedContent?key={self._api_key}"
        embeddings_list = []

        try:
            for idx, text in enumerate(texts):
                payload = {"content": {"parts": [{"text": text}]}}
                resp = await self._client.post(url, json=payload)
                if resp.status_code != 200:
                    raise CanonicalErrorMapper.map_http_error(resp.status_code, resp.text, self.id)

                data = resp.json()
                vec = data.get("embedding", {}).get("values", [])
                embeddings_list.append(Embedding(text=text, vector=vec, index=idx))

            return EmbeddingResult(embeddings=embeddings_list, model=model_name)
        except Exception as err:
            raise CanonicalErrorMapper.map_http_error(500, str(err), self.id)

    async def list_models(self) -> list[ModelInfo]:
        if not self._client:
            await self.initialize()

        assert self._client is not None
        url = f"/models?key={self._api_key or ''}"
        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                return [
                    ModelInfo(id="models/gemini-1.5-flash", name="Gemini 1.5 Flash", max_context_length=1000000),
                    ModelInfo(id="models/gemini-1.5-pro", name="Gemini 1.5 Pro", max_context_length=2000000),
                ]

            data = resp.json().get("models", [])
            models = []
            for item in data:
                m_id = item.get("name", "")
                m_name = item.get("displayName", m_id)
                ctx = item.get("inputTokenLimit", 1000000)
                models.append(ModelInfo(id=m_id, name=m_name, max_context_length=ctx))
            return models
        except Exception:
            return [
                ModelInfo(id="models/gemini-1.5-flash", name="Gemini 1.5 Flash", max_context_length=1000000),
            ]

    async def health_check(self) -> ProviderHealth:
        t0 = time.time()
        try:
            models = await self.list_models()
            latency = (time.time() - t0) * 1000.0
            return ProviderHealth(
                healthy=len(models) > 0,
                latency_ms=latency,
                model_count=len(models),
            )
        except Exception as err:
            return ProviderHealth(healthy=False, last_error=str(err))
