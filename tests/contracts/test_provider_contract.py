"""Contract tests for NexusAI BaseModelProvider implementations."""
import pytest
from typing import Type, List
from nexusai.models.base import BaseModelProvider
from nexusai.models.openai_provider import OpenAIProvider

PROVIDERS_TO_TEST: List[Type[BaseModelProvider]] = [
    OpenAIProvider,
]

@pytest.mark.parametrize("provider_cls", PROVIDERS_TO_TEST)
def test_provider_subclass_contract(provider_cls: Type[BaseModelProvider]) -> None:
    """Contract: Every provider MUST inherit from BaseModelProvider and implement chat."""
    assert issubclass(provider_cls, BaseModelProvider)
    assert hasattr(provider_cls, "chat")
    assert callable(getattr(provider_cls, "chat"))
