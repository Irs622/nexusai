"""
EmbeddingComplianceSuite for compliance verification of EmbeddingProvider implementations.
"""

from __future__ import annotations

from nexusai.memory.contracts.embedding import EmbeddingProvider


class EmbeddingComplianceSuite:
    """Reusable compliance test suite verifying any EmbeddingProvider implementation."""

    @staticmethod
    async def verify_provider_compliance(provider: EmbeddingProvider) -> None:
        """Run standard compliance assertions on target embedding provider."""
        caps = provider.capabilities
        assert caps.model_name != "", "Provider model_name must not be empty"
        assert caps.dimensions > 0, "Provider dimensions must be greater than 0"

        # 1. Single text embedding
        single_vec = await provider.embed_text("NexusAI Embedding Compliance Test")
        assert isinstance(single_vec, list), "embed_text must return a list"
        assert len(single_vec) == caps.dimensions, f"Expected dimension {caps.dimensions}, got {len(single_vec)}"
        assert all(isinstance(x, float) for x in single_vec), "Embedding values must be floats"

        # 2. Batch text embedding
        if caps.supports_batch:
            batch_texts = ["Text item 1", "Text item 2", "Text item 3"]
            batch_vecs = await provider.embed_batch(batch_texts)
            assert isinstance(batch_vecs, list), "embed_batch must return a list"
            assert len(batch_vecs) == 3, f"Expected batch size 3, got {len(batch_vecs)}"
            for vec in batch_vecs:
                assert len(vec) == caps.dimensions, f"Batch vector dimension mismatch: expected {caps.dimensions}, got {len(vec)}"
