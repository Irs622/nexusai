"""
Unit tests for Milestone 2.4.5: Vector Compliance Suite, VectorStore engines, and AST Rules A015-A020.
"""

import pytest

from nexusai.memory.vector import (
    ChromaVectorStore,
    InMemoryVectorStore,
    MockVectorStore,
    VectorComplianceSuite,
)


@pytest.mark.asyncio
async def test_in_memory_vector_compliance():
    store = InMemoryVectorStore(dimensions=4)
    await VectorComplianceSuite.verify_vector_store_compliance(store)


@pytest.mark.asyncio
async def test_mock_vector_store_compliance():
    store = MockVectorStore(dimensions=4)
    await VectorComplianceSuite.verify_vector_store_compliance(store)


@pytest.mark.asyncio
async def test_chroma_vector_store_compliance():
    store = ChromaVectorStore(dimensions=4)
    await VectorComplianceSuite.verify_vector_store_compliance(store)
