"""
Unit tests for NexusTracer and TraceSpan OpenTelemetry propagation.
"""

from nexusai.observability.tracer import NexusTracer, SpanContext


def test_tracer_span_creation_and_duration():
    tracer = NexusTracer()
    span = tracer.start_span("llm_invocation", attributes={"provider": "openrouter"})

    span.set_attribute("model", "gpt-4o")
    span.end(status="OK")

    spans = tracer.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "llm_invocation"
    assert spans[0].attributes["provider"] == "openrouter"
    assert spans[0].attributes["model"] == "gpt-4o"
    assert spans[0].duration_ms >= 0.0


def test_tracer_parent_child_context_propagation():
    tracer = NexusTracer()
    parent_span = tracer.start_span("parent_execution")

    child_span = tracer.start_span("child_execution", parent_context=parent_span.context)

    assert child_span.context.trace_id == parent_span.context.trace_id
    assert child_span.context.parent_span_id == parent_span.context.span_id
