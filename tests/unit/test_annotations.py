"""Unit tests for API stability annotations."""
from nexusai.core.annotations import stable, experimental, internal
from nexusai.tools.base import BaseTool
from nexusai.models.base import BaseModelProvider, EmbeddingProvider

def test_api_annotations_decorator() -> None:
    assert getattr(BaseTool, "__api_status__") == "stable"
    assert getattr(BaseModelProvider, "__api_status__") == "stable"
    assert getattr(EmbeddingProvider, "__api_status__") == "experimental"

    @internal
    class InternalHelper:
        pass

    assert getattr(InternalHelper, "__api_status__") == "internal"
