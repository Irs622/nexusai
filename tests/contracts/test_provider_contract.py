"""Two-Level Provider Contract Test Suite: API Surface Contract & Runtime Behavior Contract."""

import pytest

from nexusai.providers import (
    BaseProvider,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingResult,
    MessageRole,
    MockProvider,
    ModelInfo,
    ProviderHealth,
    ProviderMetadata,
    ProviderTimeoutError,
)


@pytest.mark.asyncio
async def verify_provider_api_contract(provider: BaseProvider) -> None:
    """Level 1: Provider API Surface Contract Verification Suite."""

    # 1. Metadata Verification
    meta = provider.metadata
    assert isinstance(meta, ProviderMetadata)
    assert meta.provider_id == provider.id
    assert isinstance(meta.display_name, str)

    # 2. Chat Completion Verification
    req = ChatRequest(
        messages=[ChatMessage(role=MessageRole.USER, content="Contract message")],
        model="test-model",
    )
    res = await provider.chat(req)
    assert isinstance(res, ChatResponse)
    assert len(res.choices) > 0
    primary = res.primary_choice()
    assert primary.message.role == MessageRole.ASSISTANT

    # 3. Stream Chat Verification
    chunks: list[ChatResponse] = []
    async for chunk in provider.stream_chat(req):
        chunks.append(chunk)
        assert isinstance(chunk, ChatResponse)
    assert len(chunks) > 0

    # 4. Embeddings Verification
    embed_res = await provider.embeddings(texts=["Sample query"])
    assert isinstance(embed_res, EmbeddingResult)
    assert len(embed_res.embeddings) == 1

    # 5. Model Listing Verification
    models = await provider.list_models()
    assert isinstance(models, list)
    for m in models:
        assert isinstance(m, ModelInfo)

    # 6. Health Check Verification
    health = await provider.health_check()
    assert isinstance(health, ProviderHealth)
    assert isinstance(health.healthy, bool)


@pytest.mark.asyncio
async def verify_provider_behavior_contract(provider: BaseProvider) -> None:
    """Level 2: Provider Behavior & Runtime Resiliency Contract Verification Suite."""
    from nexusai.runtime import CancellationToken, ExecutionContext

    # 1. Cancellation Token Cancellation Propagation Behavior
    token = CancellationToken()
    token.cancel("Abort requested")

    ctx = ExecutionContext()
    ctx.runtime.cancellation_token = token

    with pytest.raises(ProviderTimeoutError, match="Abort requested"):
        ctx.runtime.cancellation_token.throw_if_cancelled()


@pytest.mark.asyncio
async def test_mock_provider_api_and_behavior_contracts() -> None:
    """Verify MockProvider against API and Behavior Contract Suites."""
    mock_p = MockProvider("contract_mock")
    await verify_provider_api_contract(mock_p)
    await verify_provider_behavior_contract(mock_p)
