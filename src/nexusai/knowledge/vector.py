"""Vector Database Engine powered by ChromaDB for RAG Long-Term Memory."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import chromadb

from nexusai.core.errors import ToolExecutionError


class VectorKnowledgeBase:
    """Persistent Vector Database for long-term semantic memory storage and retrieval."""

    def __init__(
        self,
        db_path: str | Path = ".nexusai/vector_db",
        client: Any = None,
        collection_name: str = "nexusai_long_term_memory",
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.client = client
        self.collection_name = collection_name
        self.collection = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection asynchronously using asyncio.to_thread."""
        if self._initialized:
            return

        if self.client is not None:
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
        else:

            def _init_chroma() -> tuple[Any, Any]:
                self.db_path.mkdir(parents=True, exist_ok=True)
                c = chromadb.PersistentClient(path=str(self.db_path))
                col = c.get_or_create_collection(name=self.collection_name)
                return c, col

            self.client, self.collection = await asyncio.to_thread(_init_chroma)

        self._initialized = True

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def store_memory(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a text fact asynchronously into the vector database."""
        await self._ensure_initialized()
        doc_id = str(uuid.uuid4())
        meta = metadata or {"source": "user_interaction"}

        def _add() -> None:
            assert self.collection is not None
            self.collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )

        try:
            await asyncio.to_thread(_add)
            return doc_id
        except Exception as e:
            raise ToolExecutionError(f"Failed to store fact in vector database: {e}") from e

    async def search_memory(
        self,
        query: str,
        n_results: int = 3,
    ) -> list[str]:
        """Search long-term memory for semantically relevant facts."""
        await self._ensure_initialized()

        def _query() -> list[str]:
            assert self.collection is not None
            count = self.collection.count()
            if count == 0:
                return []
            res = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, count),
            )
            documents = res.get("documents", [])
            if documents and len(documents) > 0:
                return [doc for doc in documents[0] if doc]
            return []

        try:
            return await asyncio.to_thread(_query)
        except Exception as e:
            raise ToolExecutionError(f"Failed to search vector database: {e}") from e
