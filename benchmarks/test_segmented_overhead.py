"""Segmented Runtime Overhead Benchmark measuring per-phase execution latency breakdown."""

import time
import pytest

from nexusai.providers import ChatMessage, ChatRequest, MessageRole, MockProvider
from nexusai.providers.translators import OpenAITranslator
from nexusai.runtime import ExecutionContext, ExecutionEngine, ExecutionReport, Trace


@pytest.mark.asyncio
async def test_segmented_runtime_overhead_breakdown() -> None:
    """Benchmark per-phase latency breakdown across Routing, Middleware, Translator, Trace, and ExecutionReport."""
    p = MockProvider("segmented_mock")
    engine = ExecutionEngine()
    engine.manager.registry.register(p)

    req = ChatRequest(messages=[ChatMessage(role=MessageRole.USER, content="Segmented overhead test")])
    translator = OpenAITranslator()

    # 1. Routing Overhead
    t0 = time.perf_counter()
    decision_p = await engine.router.route(request=req)
    t1 = time.perf_counter()
    routing_ms = (t1 - t0) * 1000.0

    # 2. Translator Overhead
    wire_req = translator.from_canonical_request(req)
    t2 = time.perf_counter()
    raw_payload = {
        "id": "mock_1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}}],
    }
    canonical_res = translator.to_canonical_response(raw_payload, provider_id="segmented_mock")
    t3 = time.perf_counter()
    translator_ms = (t3 - t2) * 1000.0

    # 3. Tracing Overhead
    trace = Trace()
    t4 = time.perf_counter()
    span = trace.start_span("routing")
    span.finish()
    t5 = time.perf_counter()
    tracing_ms = (t5 - t4) * 1000.0

    # 4. ExecutionReport Overhead
    t6 = time.perf_counter()
    report = ExecutionReport(
        request_id="r1",
        provider_id=decision_p.id,
        model="mock",
        latency_ms=1.0,
    )
    t7 = time.perf_counter()
    report_ms = (t7 - t6) * 1000.0

    total_ms = routing_ms + translator_ms + tracing_ms + report_ms

    print("\n=== Segmented Runtime Overhead Breakdown ===")
    print(f"Routing:           {routing_ms:.4f} ms")
    print(f"Translator:        {translator_ms:.4f} ms")
    print(f"Tracing:           {tracing_ms:.4f} ms")
    print(f"ExecutionReport:   {report_ms:.4f} ms")
    print(f"Total Framework:   {total_ms:.4f} ms")

    assert total_ms < 2.0, f"Total segmented overhead exceeded 2.0ms: {total_ms:.4f}ms"
